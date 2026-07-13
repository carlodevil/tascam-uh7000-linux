from __future__ import annotations

import unittest

from uh7000.protocol import (
    ClockSource,
    MemoryTransport,
    REQUEST_SELECTOR_STATUS,
    REQUEST_STATE_PAGE,
    StatePage,
    parse_vendor_status_packets,
    read_selector_status,
    read_state_page,
    set_clock_source,
    validate_clock_source_cycle,
)


class ProtocolTests(unittest.TestCase):
    def test_selector_is_one_byte_read(self) -> None:
        transport = MemoryTransport({(REQUEST_SELECTOR_STATUS, 0, 0, 1): b"\x02"})
        self.assertEqual(2, read_selector_status(transport))
        self.assertEqual((REQUEST_SELECTOR_STATUS, 0, 0, 1, 1000), transport.requests[0])

    def test_only_verified_pages_can_be_read(self) -> None:
        transport = MemoryTransport({})
        with self.assertRaises(ValueError):
            read_state_page(transport, 0x0002)

    def test_state_page_classification(self) -> None:
        self.assertTrue(StatePage(0x007C, bytes([0xFF]) * 512).is_all_ff)
        self.assertTrue(StatePage(0x007C, bytes(512)).is_all_zero)

    def test_verified_page_read(self) -> None:
        data = bytes(range(256)) * 2
        transport = MemoryTransport({(REQUEST_STATE_PAGE, 0, 0x1F00, 512): data})
        page = read_state_page(transport, 0x1F00)
        self.assertEqual(data, page.payload)

    def test_vendor_status_packets_are_strictly_framed(self) -> None:
        packets = parse_vendor_status_packets(b"\x0b\xb0\x6b\x00\x0b\xb0\x6c\x01")
        self.assertEqual(0x6B, packets[0].control)
        self.assertEqual(1, packets[1].value)
        with self.assertRaises(ValueError):
            parse_vendor_status_packets(b"\x0b\xb0\x6b")
        with self.assertRaises(ValueError):
            parse_vendor_status_packets(b"\x00\x00\x6b\x00")

    def test_clock_source_write_requires_matching_readback(self) -> None:
        transport = MemoryTransport({(REQUEST_SELECTOR_STATUS, 0, 0, 1): [b"\x02", b"\x00"]})
        self.assertEqual(ClockSource.INTERNAL, set_clock_source(transport, ClockSource.INTERNAL))
        self.assertEqual((REQUEST_SELECTOR_STATUS, 0, 0, b"", 1000), transport.writes[0])

    def test_clock_source_write_rolls_back_on_mismatch(self) -> None:
        transport = MemoryTransport(
            {(REQUEST_SELECTOR_STATUS, 0, 0, 1): [b"\x02", b"\x07", b"\x02"]}
        )
        with self.assertRaisesRegex(IOError, "previous state restored"):
            set_clock_source(transport, ClockSource.INTERNAL)
        self.assertEqual([0, 2], [write[1] for write in transport.writes])

    def test_clock_source_write_rolls_back_after_write_error(self) -> None:
        transport = MemoryTransport(
            {(REQUEST_SELECTOR_STATUS, 0, 0, 1): [b"\x02", b"\x02"]},
            write_results=[OSError("usb timeout"), 0],
        )
        with self.assertRaisesRegex(IOError, "previous state restored"):
            set_clock_source(transport, ClockSource.INTERNAL)
        self.assertEqual([0, 2], [write[1] for write in transport.writes])

    def test_clock_source_cycle_restores_automatic(self) -> None:
        transport = MemoryTransport(
            {
                (REQUEST_SELECTOR_STATUS, 0, 0, 1): [
                    b"\x02",
                    b"\x02",
                    b"\x00",
                    b"\x00",
                    b"\x00",
                    b"\x02",
                    b"\x02",
                ]
            }
        )
        cycle = validate_clock_source_cycle(transport)
        self.assertEqual(ClockSource.AUTOMATIC, cycle.initial)
        self.assertEqual(ClockSource.INTERNAL, cycle.tested)
        self.assertEqual(ClockSource.AUTOMATIC, cycle.final)
        self.assertEqual([0, 2], [write[1] for write in transport.writes])


if __name__ == "__main__":
    unittest.main()
