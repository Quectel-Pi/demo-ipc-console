import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import app
import onvif_discovery


class AppHelperTests(unittest.TestCase):
    def test_xml_escapes_reserved_characters(self):
        self.assertEqual(app.xml('a&<b>"'), "a&amp;&lt;b&gt;&quot;")

    def test_tag_accepts_namespaced_elements(self):
        payload = "<root><tt:Model>Demo Camera</tt:Model></root>"
        self.assertEqual(app.tag(payload, "Model"), "Demo Camera")

    def test_recording_command_uses_target_and_optional_audio(self):
        target = PROJECT_ROOT / "recordings" / "demo.mp4"
        command = app.recording_command("rtsp://example.invalid/stream", target)
        self.assertEqual(command[0], "ffmpeg")
        self.assertIn("0:a:0?", command)
        self.assertEqual(command[-1], str(target))


class DiscoveryParserTests(unittest.TestCase):
    def test_parse_probe_match_extracts_device_fields(self):
        payload = b"""<?xml version="1.0"?>
        <e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
          xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing"
          xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery">
          <e:Body><d:ProbeMatches><d:ProbeMatch>
            <a:EndpointReference><a:Address>urn:uuid:camera-1</a:Address></a:EndpointReference>
            <d:XAddrs>http://192.0.2.10/onvif/device_service</d:XAddrs>
            <d:Scopes>onvif://www.onvif.org/name/Demo</d:Scopes>
          </d:ProbeMatch></d:ProbeMatches></e:Body>
        </e:Envelope>"""
        result = onvif_discovery.parse_probe_match(payload, "192.0.2.10", "eth0")
        self.assertEqual(result["endpoint_id"], "urn:uuid:camera-1")
        self.assertEqual(result["source_ip"], "192.0.2.10")
        self.assertEqual(result["interface"], "eth0")
        self.assertEqual(result["xaddrs"], ["http://192.0.2.10/onvif/device_service"])

    def test_parse_probe_match_rejects_invalid_xml(self):
        self.assertIsNone(onvif_discovery.parse_probe_match(b"not xml", "192.0.2.10", "eth0"))


if __name__ == "__main__":
    unittest.main()
