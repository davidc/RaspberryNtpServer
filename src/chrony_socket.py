"""
Chrony UDP client module for direct communication with chronyd.
"""

from datetime import datetime, timedelta, timezone
import ipaddress
import socket
import string
import struct
import logging
import threading
import time
import random
from typing import Any, Optional
from chrony import ChronyClient


# Protocol reference is candm.h in the chrony source code. Implementation reference is client.c.

# Protocol constants from candm.h
PROTO_VERSION_NUMBER = 6
DEFAULT_CANDM_PORT = 323
FLOAT_EXP_BITS = 7
FLOAT_COEF_BITS = 32 - FLOAT_EXP_BITS

# IP address types
IPADDR_INET4 = 1
IPADDR_INET6 = 2
# unimplemented here IPADDR_ID = 3

# Packet types
PKT_TYPE_CMD_REQUEST = 1
PKT_TYPE_CMD_REPLY = 2

# Request codes
REQ_N_SOURCES = 14
REQ_SOURCE_DATA = 15
REQ_TRACKING = 33

# Reply codes
RPY_N_SOURCES = 2
RPY_SOURCE_DATA = 3
RPY_TRACKING = 5

# Status codes
STT_SUCCESS = 0
STT_FAILED = 1

# source types
RPY_SD_MD_CLIENT = 0
RPY_SD_MD_PEER = 1
RPY_SD_MD_REF = 2

# source states
RPY_SD_ST_SELECTED = 0

#### HEADER

# CMD_Request struct.
# version(uint8_t)
# pkt_type(uint8_t)
# reserved(2x uint8_t)
# command(uint16_t)
# attempt(uint16_t)
# sequence (uint32_t)
# pad1 (uint32_t)
# pad2 (uint32_t)
CMD_REQUEST_HEADER_STRUCT = "!BBxxHHIxxxxxxxx"

# CMD_Reply struct.
# version(uint8_t)
# pkt_type(uint8_t)
# reserved(2x uint8_t)
# command(uint16_t)
# format(uint16_t)
# status(uint16_t)
# pad1 (uint16_t)
# pad2+3 (2x uint16_t)
# sequence (uint32_t)
# pad4 (uint32_t)
# pad5 (uint32_t)
CMD_REPLY_HEADER_STRUCT = "!BBHHHHHIIII"
CMD_REPLY_HEADER_SIZE = struct.calcsize(CMD_REPLY_HEADER_STRUCT)


#### N_SOURCES request

# REQ_N_SOURCES struct.
REQ_N_SOURCES_STRUCT = ""

# RPY_N_SOURCES struct.
#  uint32_t n_sources;
RPY_N_SOURCES_STRUCT = "!I"
RPY_N_SOURCES_SIZE = struct.calcsize(RPY_N_SOURCES_STRUCT)
REQ_N_SOURCES_PADDING = max(
    struct.calcsize(RPY_N_SOURCES_STRUCT) - struct.calcsize(REQ_N_SOURCES_STRUCT), 0
)


#### SOURCE_DATA request

# REQ_Source_Data struct
#   int32_t index;
REQ_SOURCE_DATA_STRUCT = "!I"
REQ_SOURCE_DATA_SIZE = struct.calcsize(REQ_SOURCE_DATA_STRUCT)

# typedef struct {
#   IPAddr ip_addr;:
#        union {
#          uint32_t in4;
#          uint8_t in6[16];
#           uint32_t id;
#         } addr;
#          uint16_t family;
#          uint16_t _pad;
#   int16_t poll;
#   uint16_t stratum;
#   uint16_t state;
#   uint16_t mode;
#   uint16_t flags;
#   uint16_t reachability;
#   uint32_t  since_sample;
#   Float orig_latest_meas;
#   Float latest_meas;
#   Float latest_meas_err;
#   int32_t EOR;
# } RPY_Source_Data;
RPY_SOURCE_DATA_STRUCT = "!16sHxxhHHHHHIIII"
RPY_SOURCE_DATA_SIZE = struct.calcsize(RPY_SOURCE_DATA_STRUCT)

REQ_SOURCE_DATA_PADDING = max(
    struct.calcsize(RPY_SOURCE_DATA_STRUCT) - struct.calcsize(REQ_SOURCE_DATA_STRUCT), 0
)


#### TRACKING request

# REQ_TRACKING struct (empty)
REQ_TRACKING_STRUCT = ""

# typedef struct {
#   uint32_t ref_id;
#   IPAddr ip_addr;
#        union {
#          uint32_t in4;
#          uint8_t in6[16];
#           uint32_t id;
#         } addr;
#          uint16_t family;
#          uint16_t _pad;
#   uint16_t stratum;
#   uint16_t leap_status;
#   Timespec ref_time;
#     typedef struct {
#        uint32_t tv_sec_high;
#        uint32_t tv_sec_low;
#        uint32_t tv_nsec;
#     } Timespec;
#   Float current_correction;
#   Float last_offset;
#   Float rms_offset;
#   Float freq_ppm;
#   Float resid_freq_ppm;
#   Float skew_ppm;
#   Float root_delay;
#   Float root_dispersion;
#   Float last_update_interval;
#   int32_t EOR;
# } RPY_Tracking;

RPY_TRACKING_STRUCT = "!I16sHxxHHIIIIIIIIIIII"
RPY_TRACKING_SIZE = struct.calcsize(RPY_TRACKING_STRUCT)

REQ_TRACKING_PADDING = max(
    struct.calcsize(RPY_TRACKING_STRUCT) - struct.calcsize(REQ_TRACKING_STRUCT), 0
)


def format_signed_nanoseconds(s: float) -> str:
    # TODO move this to our print code once we're no longer storing strings in our statistics.

    x = abs(s)

    if x < 9999.5e-9:
        return f"{s * 1e9:+.0f}ns"
    elif x < 9999.5e-6:
        return f"{s * 1e6:+.0f}us"
    elif x < 9999.5e-3:
        return f"{s * 1e3:+.0f}ms"
    elif x < 999.5:
        return f"{s:+.1f}s"
    elif x < 99999.5:
        return f"{s:+.0f}s"
    elif x < 99999.5 * 60:
        return f"{s / 60:+.0f}m"
    elif x < 99999.5 * 3600:
        return f"{s / 3600:+.0f}h"
    elif x < 99999.5 * 3600 * 24:
        return f"{s / (3600 * 24):+.0f}d"
    else:
        return f"{s / (3600 * 24 * 365):+.0f}y"


class ChronySocketClient(ChronyClient):
    """Chrony client implementation using direct socket connection to chronyd."""

    def __init__(
        self,
        update_interval: Optional[float],
        host: Optional[str] = None,
        port: Optional[int] = None,
    ):
        """
        Initialize the Chrony socket client and start the background thread.

        Args:
            update_interval: Time in seconds between updates (-1 to not start thread for testing purposes)
            host: Hostname or IP address of chronyd (default 127.0.0.1)
            port: Port number of chronyd (default 323)
        """
        super().__init__(update_interval)
        self.host = host or "127.0.0.1"
        self.port = port or DEFAULT_CANDM_PORT
        self._sock: Optional[socket.socket] = None

        if update_interval and update_interval > 0:
            self._thread = threading.Thread(target=self._chrony_thread, daemon=True)
            self._thread.start()

    def _chrony_thread(self):
        """Background thread that periodically updates Chrony statistics."""
        while True:
            try:
                while True:
                    self._update_statistics()
                    time.sleep(self.update_interval)
            except Exception as e:
                self.log.warning(f"Error updating Chrony statistics: {e}")
            finally:
                with self._lock:
                    self._stratum = None
                    self._system_time_offset = None
                    self._is_locked = False
                    self._is_pps = False
                    self._source = None
                    self._adjusted_offset = None
                self._close_socket()

            self.log.info("Waiting 5 seconds before retrying chrony connection...")
            time.sleep(5)

    def _connect_socket(self) -> bool:
        """Create UDP socket for chronyd communication."""
        try:
            if self._sock:
                self._close_socket()

            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.settimeout(5.0)  # 5 second timeout
            self.log.info(f"Created UDP socket for chronyd at {self.host}:{self.port}")
            return True
        except Exception as e:
            self.log.warning(
                f"Failed to create UDP socket for chronyd at {self.host}:{self.port}: {e}"
            )
            self._close_socket()
            return False

    def _close_socket(self):
        """Close the socket connection."""
        if self._sock:
            try:
                self._sock.close()
            except:
                pass
            self._sock = None

    def _send_request(
        self,
        command: int,
        request_padding: int,
        expected_reply_format: int,
        data: bytes = b"",
    ) -> bytes:
        """
        Send a request to chronyd and return the reply data.

        Args:
            command: Request command code
            requested_reply_format: The format of the reply data excepted
            data: Request data payload

        Returns:
            Reply data or None if failed

        Raises:
            socket.timeout if no reply is received within the timeout period
        """
        if not self._sock and not self._connect_socket():
            raise RuntimeError("Attempted to send request with socket not initialised")

        try:
            sequence = random.randint(0, 0xFFFFFFFF)

            # Pack the request header
            request = struct.pack(
                CMD_REQUEST_HEADER_STRUCT,
                PROTO_VERSION_NUMBER,
                PKT_TYPE_CMD_REQUEST,
                command,
                0,  # Attempt number
                sequence,
            )

            request += data

            # Pad to the necessary number of request bytes else the command is ignored due to anti-amplification
            # measures in version 6 of the protocol. The extra 8 needs to be investigated, partly it will be
            # because each command has a EOR in the packet that we don't bother with in Python, but I've not
            # explained the other 4.
            request += b"\x00" * (request_padding + 8)

            # Send request to chronyd
            self._sock.sendto(request, (self.host, self.port)) # pyright: ignore[reportOptionalMemberAccess]

            # Receive reply (UDP datagram) - accept from any address
            # TODO keep receiving until we get a reply matching our sequence number, or timeout after a certain period
            reply, _ = self._sock.recvfrom(4096)  # pyright: ignore[reportOptionalMemberAccess] # Max UDP packet size

            if len(reply) < CMD_REPLY_HEADER_SIZE:
                raise RuntimeError(
                    f"Received reply packet is too short, got {len(reply)} bytes but expected at least {CMD_REPLY_HEADER_SIZE}"
                )

            # Unpack the response header
            (
                reply_version,
                reply_pkt_type,
                _,
                reply_command,
                reply_format,
                reply_status,
                _,
                _,
                reply_sequence,
                _,
                _,
            ) = struct.unpack(CMD_REPLY_HEADER_STRUCT, reply[0:CMD_REPLY_HEADER_SIZE])

            if reply_version != PROTO_VERSION_NUMBER:
                raise RuntimeError(
                    f"Received packet with unknown protocol version {reply_version}"
                )

            if reply_pkt_type != PKT_TYPE_CMD_REPLY:
                raise RuntimeError(
                    f"Received packet is not a reply, got packet type {reply_pkt_type}"
                )

            if reply_command != command:
                raise RuntimeError(
                    "Received packet with a mismatched command, got {reply_command} but expected {command}"
                )

            # if reply_format != expected_reply_format:
            # TODO why doesn't this work
            # raise RuntimeError(
            #     f"Reply format mismatch: got {reply_format} but expected {expected_reply_format}"
            # )

            if reply_status != STT_SUCCESS:
                raise RuntimeError(
                    f"Reply packet was not a success, received STT_ status code {reply_status}"
                )

            if reply_sequence != sequence:
                raise RuntimeError(
                    f"Received packet with mismatched sequence number, got {reply_sequence} but expected {sequence}"
                )

            # Extract reply data
            reply_data = reply[CMD_REPLY_HEADER_SIZE:]
            return reply_data

        except Exception as e:
            self.log.warning(f"Socket communication error: {e}")
            self._close_socket()
            raise

    def _decode_network_float32(self, float32_data: int) -> float:
        """Decode a 32-bit float from the network format used by chronyd.

        As per candm.h: "32-bit floating-point format consisting of 7-bit signed exponent and 25-bit signed
        coefficient without hidden bit. The result is calculated as: 2^(exp - 25) * coef."

        Code based on UTI_FloatNetworkToHost.

        Args:
            float32_data: The 32-bit data (passed as uint32_t) received from chronyd, representing the float.

        Returns:
            The decoded float value.
        """

        # Extract exponent (top 7 bits)
        exp: int = float32_data >> FLOAT_COEF_BITS
        if exp >= (1 << (FLOAT_EXP_BITS - 1)):
            exp -= 1 << FLOAT_EXP_BITS
        exp -= FLOAT_COEF_BITS

        # Extract coefficient (bottom 25 bits)
        coef: int = float32_data & ((1 << FLOAT_COEF_BITS) - 1)
        if coef >= (1 << (FLOAT_COEF_BITS - 1)):
            coef -= 1 << FLOAT_COEF_BITS

        return coef * pow(2.0, exp)

    def _decode_network_timespec(
        self, sec_high: int, sec_low: int, nsec: int
    ) -> datetime:
        """Decode a timespec from the network format of struct timespec used by chronyd.

        Args:
            sec_high: The high 32 bits of the seconds since Unix epoch
            sec_low: The low 32 bits of the seconds since Unix epoch
            nsec: The nanoseconds part
        Returns:
            The decoded datetime value.
        """
        total_seconds: int = (sec_high << 32) | sec_low

        # Avoid loss of precision in float by first constructing the second time
        base_time: datetime = datetime.fromtimestamp(total_seconds, tz=timezone.utc)

        # Now add the nanoseconds as a timedelta to the base time
        return base_time + timedelta(microseconds=nsec // 1000)

    def _get_tracking(self) -> dict[str, Any]:
        """
        Get tracking data equivalent to 'chronyc tracking'.

        Returns:
            Dict of data
        """

        # First get the number of sources
        tracking_data = self._send_request(
            REQ_TRACKING, REQ_TRACKING_PADDING, RPY_TRACKING
        )

        (
            ref_id,
            ip_data,
            family,
            stratum,
            leap_status,
            ref_time_high,
            ref_time_low,
            ref_time_nsec,
            current_correction,
            last_offset,
            rms_offset,
            freq_ppm,
            resid_freq_ppm,
            skew_ppm,
            root_delay,
            root_dispersion,
            last_update_interval,
        ) = struct.unpack(RPY_TRACKING_STRUCT, tracking_data[:RPY_TRACKING_SIZE])

        tracking = {
            "ref_id": ref_id,
            "stratum": stratum,
            "leap_status": leap_status,
            "ref_time": self._decode_network_timespec(
                ref_time_high, ref_time_low, ref_time_nsec
            ),
            "current_correction": self._decode_network_float32(current_correction),
            "last_offset": self._decode_network_float32(last_offset),
            "rms_offset": self._decode_network_float32(rms_offset),
            "freq_ppm": self._decode_network_float32(freq_ppm),
            "resid_freq_ppm": self._decode_network_float32(resid_freq_ppm),
            "skew_ppm": self._decode_network_float32(skew_ppm),
            "root_delay": self._decode_network_float32(root_delay),
            "root_dispersion": self._decode_network_float32(root_dispersion),
            "last_update_interval": self._decode_network_float32(last_update_interval),
        }

        if family == IPADDR_INET4:
            tracking["ip_addr"] = ipaddress.IPv4Address(ip_data[:4])
        elif family == IPADDR_INET6:
            tracking["ip_addr"] = ipaddress.IPv6Address(ip_data[:16])
        else:
            tracking["ip_addr"] = None

        return tracking

    def _get_sources(
        self,
    ) -> list:
        """
        Get sources data equivalent to 'chronyc sources'.

        Returns:
            List of sources
        """
        # First get the number of sources
        n_sources_data = self._send_request(
            REQ_N_SOURCES, REQ_N_SOURCES_PADDING, RPY_N_SOURCES
        )

        n_sources = struct.unpack(
            RPY_N_SOURCES_STRUCT, n_sources_data[:RPY_N_SOURCES_SIZE]
        )[0]

        if n_sources == 0:
            return []

        # Get data for the each source (index 0)
        sources = []

        for source_index in range(n_sources):

            request = struct.pack(REQ_SOURCE_DATA_STRUCT, source_index)

            source_data = self._send_request(
                REQ_SOURCE_DATA, REQ_SOURCE_DATA_PADDING, RPY_SOURCE_DATA, request
            )

            (
                ip_data,
                family,
                poll,
                stratum,
                state,
                mode,
                flags,
                reachability,
                since_sample,
                orig_latest_meas,
                latest_meas,
                latest_meas_err,
            ) = struct.unpack(
                RPY_SOURCE_DATA_STRUCT, source_data[:RPY_SOURCE_DATA_SIZE]
            )

            source_info = {
                "poll": poll,
                "stratum": stratum,
                "state": state,
                "mode": mode,
                "flags": flags,
                "reachability": reachability,
                "since_sample": since_sample,
                "orig_latest_meas": self._decode_network_float32(orig_latest_meas),
                "latest_meas": self._decode_network_float32(latest_meas),
                "latest_meas_err": self._decode_network_float32(latest_meas_err),
            }

            # if mode is RPY_SD_MD_REF then the IPv4 address is fake, it's the ref name as up to 4 bytes of ASCII
            if mode == RPY_SD_MD_REF and family == IPADDR_INET4:
                source_info["ref"] = "".join(
                    filter(
                        lambda x: x in string.printable,
                        struct.unpack("!4s", ip_data[:4])[0].decode(encoding="ascii"),
                    )
                )
            elif family == IPADDR_INET4:
                source_info["ip_addr"] = ipaddress.IPv4Address(ip_data[:4])
            elif family == IPADDR_INET6:
                source_info["ip_addr"] = ipaddress.IPv6Address(ip_data[:16])
            else:
                source_info["ip_addr"] = None

            sources.append(source_info)

        return sources

    def _update_statistics(self) -> None:
        """
        Update Chrony statistics.
        """

        new_stratum = None
        new_system_time_offset = None
        new_is_locked = False
        new_is_pps = False
        new_source = None
        new_adjusted_offset = None

        # Get tracking data
        tracking = self._get_tracking()

        new_stratum = tracking["stratum"]
        new_system_time_offset = tracking["current_correction"]

        # Get sources data
        sources = self._get_sources()

        # Looking for a source matching "#* PPS" i.e. mode is ref and state is selected and source name is PPS
        for source in sources:
            if (
                source["mode"] == RPY_SD_MD_REF
                and source["state"] == RPY_SD_ST_SELECTED
                and "ref" in source
                and source["ref"] is not None
                and source["ref"][:3] == "PPS"
            ):
                new_is_locked = True
                new_is_pps = True
                new_source = source["ref"]

                new_adjusted_offset = format_signed_nanoseconds(
                    source["latest_meas"]
                )  # format to string to match for now

                break

        # If we haven't found a PPS source, look for a source matching "^*" i.e. mode is client and state is selected
        if new_is_locked is False:
            for source in sources:
                if (
                    source["mode"] == RPY_SD_MD_CLIENT
                    and source["state"] == RPY_SD_ST_SELECTED
                ):
                    new_is_locked = True
                    new_is_pps = False

                    if "ip_addr" in source:
                        try:
                            new_source = socket.gethostbyaddr(str(source["ip_addr"]))[0]
                        except Exception as e:
                            self.log.debug(
                                f"Unable to resolve {source['ip_addr']}: {e}"
                            )
                            new_source = str(source["ip_addr"])
                    else:
                        new_source = "Unknown"

                    new_adjusted_offset = format_signed_nanoseconds(
                        source["latest_meas"]
                    )  # format to string to match for now
                    break

        # Update state via superclass method
        self._update_state(
            stratum=new_stratum,
            system_time_offset=new_system_time_offset,
            is_locked=new_is_locked,
            is_pps=new_is_pps,
            source=new_source,
            adjusted_offset=new_adjusted_offset,
        )


if __name__ == "__main__":
    # Simple test to print tracking and sources data
    client = ChronySocketClient(host="192.168.10.249", update_interval=-1)

    from pprint import pprint

    sources = client._get_sources()
    print("sources=", end="")
    pprint(sources)

    tracking = client._get_tracking()
    print("tracking=", end="")
    pprint(tracking)

    client._update_statistics()

    print(f"Stratum: {client.stratum}")
    print(f"System Time Offset: {client.system_time_offset}")
    print(f"Is Locked: {client.is_locked}")
    print(f"Is PPS: {client.is_pps}")
    print(f"Source: {client.source}")
    print(f"Adjusted Offset: {client.adjusted_offset}")
