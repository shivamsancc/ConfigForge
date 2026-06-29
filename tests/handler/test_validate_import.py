"""
Integration tests for the validate-import endpoints.

Each test class creates an isolated FastAPI TestClient backed by a temporary
SQLite database.  ``storage.init()`` is also called so that direct storage
calls (``storage.list_devices()``, ``storage.upsert_device()``, etc.) share
the same database as the HTTP layer.

Endpoints exercised
-------------------
POST /api/devices/validate-import   body: {"devices": [...]}
POST /api/bandwidth/validate-import body: {"rows": [...]}
POST /api/subnets/validate-import   body: {"subnets": [...]}

Contracts verified
------------------
1.  HTTP 200 with {"findings": [...]} on valid payload.
2.  findings is a list (may be empty for clean data).
3.  Each finding has code, severity, category, message keys.
4.  severity is "error" or "warning" exclusively.
5.  category is one of the four defined values.
6.  Validate-import NEVER writes to the database.
7.  HTTP 400 when the required list key is missing or not a list.
8.  Device findings include DEVICE_INVALID_IP for bad IPs.
9.  Bandwidth endpoint cross-refs against existing DB devices (BW_ORPHANED).
10. Subnet findings include SUBNET_INVALID_CIDR for bad CIDRs.

Run from the repository root:
    python3 -m pytest tests/handler/test_validate_import.py -v
    python3 -m unittest tests/handler/test_validate_import.py   (also works)
"""
import os
import sys
import tempfile
import unittest

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import core.storage as storage
from app import create_app


# ---------------------------------------------------------------------------
# Test client fixture
# ---------------------------------------------------------------------------

class _TestClient:
    """Create an isolated FastAPI TestClient for one test class."""

    def __init__(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmpdir.name, 'test.db')

        # Initialise the storage shim — used by tests that call storage.*
        # functions directly to inspect or seed the database.
        storage.init(self.db_path)

        # Build the FastAPI app reusing the same ServiceContainer so HTTP
        # requests and direct storage calls operate on the same data.
        self.client = TestClient(
            create_app(container=storage._container),
            raise_server_exceptions=False,
        )

    def post(self, path: str, payload: dict):
        """POST *payload* as JSON, return (status_code, response_dict)."""
        r = self.client.post(path, json=payload)
        return r.status_code, r.json()

    def stop(self):
        self._tmpdir.cleanup()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _post(tc: _TestClient, path: str, payload: dict):
    """Module-level helper kept for symmetry with the original test layout."""
    return tc.post(path, payload)


def _clean_device(ip='192.0.2.1', name='Router1', region='us-east'):
    return {
        'IP': ip,
        'Device': name,
        'Collector Region': region,
        'snmpUser': 'admin',
        'authProtocol': 'SHA',
        'authKey': 'authpass',
        'privProtocol': 'AES',
        'privKey': 'privpass',
    }


def _clean_bw_row(ip='192.0.2.1', iface='GigabitEthernet0/0', bw='1 Gbps'):
    return {'IP': ip, 'Interface': iface, 'Allocated BW': bw}


def _clean_subnet(cidr='192.0.2.0/24', desc='Test Net'):
    return {'CIDR': cidr, 'Description': desc}


# ---------------------------------------------------------------------------
# Device validate-import tests
# ---------------------------------------------------------------------------

class TestValidateImportDevices(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._srv = _TestClient()
        cls.client = cls._srv.client

    @classmethod
    def tearDownClass(cls):
        cls._srv.stop()

    def _post(self, payload):
        return self._srv.post('/api/devices/validate-import', payload)

    # --- HTTP contract ---

    def test_returns_200_with_findings_key(self):
        status, data = self._post({'devices': [_clean_device()]})
        self.assertEqual(status, 200)
        self.assertIn('findings', data)

    def test_findings_is_list(self):
        _, data = self._post({'devices': [_clean_device()]})
        self.assertIsInstance(data['findings'], list)

    def test_empty_list_is_accepted(self):
        status, data = self._post({'devices': []})
        self.assertEqual(status, 200)
        self.assertEqual(data['findings'], [])

    def test_missing_key_returns_400(self):
        status, data = self._post({})
        self.assertEqual(status, 400)
        self.assertIn('error', data)

    def test_non_list_value_returns_400(self):
        status, data = self._post({'devices': 'not-a-list'})
        self.assertEqual(status, 400)

    # --- Finding schema contract ---

    def test_finding_has_required_keys(self):
        _, data = self._post({'devices': [{'IP': 'not-an-ip', 'Device': 'X'}]})
        findings = data['findings']
        self.assertTrue(len(findings) > 0, 'expected at least one finding')
        for f in findings:
            self.assertIn('code', f)
            self.assertIn('severity', f)
            self.assertIn('category', f)
            self.assertIn('message', f)

    def test_severity_values_are_valid(self):
        _, data = self._post({'devices': [{'IP': 'not-an-ip', 'Device': 'X'}]})
        for f in data['findings']:
            self.assertIn(f['severity'], ('error', 'warning'))

    def test_category_values_are_valid(self):
        _, data = self._post({'devices': [{'IP': 'not-an-ip', 'Device': 'X'}]})
        valid_categories = {'inventory', 'snmp', 'network', 'generation'}
        for f in data['findings']:
            self.assertIn(f['category'], valid_categories)

    # --- Validation logic ---

    def test_clean_device_produces_no_findings(self):
        _, data = self._post({'devices': [_clean_device()]})
        self.assertEqual(data['findings'], [])

    def test_invalid_ip_produces_finding(self):
        _, data = self._post({'devices': [{'IP': '999.999.999.999', 'Device': 'X',
                                            'Collector Region': 'us-east'}]})
        codes = [f['code'] for f in data['findings']]
        self.assertIn('DEVICE_INVALID_IP', codes)

    def test_blank_ip_produces_device_no_ip_finding(self):
        _, data = self._post({'devices': [{'IP': '', 'Device': 'X',
                                            'Collector Region': 'us-east'}]})
        codes = [f['code'] for f in data['findings']]
        self.assertIn('DEVICE_NO_IP', codes)

    def test_missing_region_produces_finding(self):
        d = _clean_device()
        d['Collector Region'] = ''
        _, data = self._post({'devices': [d]})
        codes = [f['code'] for f in data['findings']]
        self.assertIn('DEVICE_NO_REGION', codes)

    def test_duplicate_ip_produces_finding(self):
        d1 = _clean_device(ip='192.0.2.1', name='A')
        d2 = _clean_device(ip='192.0.2.1', name='B')
        _, data = self._post({'devices': [d1, d2]})
        codes = [f['code'] for f in data['findings']]
        self.assertIn('DEVICE_DUPLICATE_IP', codes)

    def test_findings_sorted_errors_before_warnings(self):
        d_no_ip = {'IP': '', 'Device': 'NoIp', 'Collector Region': 'us-east'}
        d_no_creds = _clean_device(ip='192.0.2.2', name='NoCreds')
        d_no_creds['snmpUser'] = ''
        _, data = self._post({'devices': [d_no_ip, d_no_creds]})
        findings = data['findings']
        severities = [f['severity'] for f in findings]
        last_error_idx = max((i for i, s in enumerate(severities) if s == 'error'), default=-1)
        first_warn_idx = min((i for i, s in enumerate(severities) if s == 'warning'), default=len(severities))
        self.assertLessEqual(last_error_idx, first_warn_idx,
                             'errors should appear before warnings in sorted output')

    # --- No database write ---

    def test_validate_does_not_write_to_db(self):
        before = len(storage.list_devices())
        self._post({'devices': [_clean_device(ip='192.0.2.99', name='ShouldNotPersist')]})
        after = len(storage.list_devices())
        self.assertEqual(before, after, 'validate-import must not write to the database')


# ---------------------------------------------------------------------------
# Bandwidth validate-import tests
# ---------------------------------------------------------------------------

class TestValidateImportBandwidth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._srv = _TestClient()
        cls.client = cls._srv.client

    @classmethod
    def tearDownClass(cls):
        cls._srv.stop()

    def _post(self, payload):
        return self._srv.post('/api/bandwidth/validate-import', payload)

    def test_returns_200_with_findings_key(self):
        status, data = self._post({'rows': [_clean_bw_row()]})
        self.assertEqual(status, 200)
        self.assertIn('findings', data)

    def test_findings_is_list(self):
        _, data = self._post({'rows': []})
        self.assertIsInstance(data['findings'], list)

    def test_missing_key_returns_400(self):
        status, data = self._post({'devices': []})
        self.assertEqual(status, 400)

    def test_non_list_value_returns_400(self):
        status, _ = self._post({'rows': 42})
        self.assertEqual(status, 400)

    def test_orphaned_bw_produces_finding_when_device_absent(self):
        _, data = self._post({'rows': [_clean_bw_row(ip='192.0.2.50')]})
        codes = [f['code'] for f in data['findings']]
        self.assertIn('BW_ORPHANED', codes)

    def test_duplicate_interface_produces_finding(self):
        row1 = _clean_bw_row(ip='192.0.2.1', iface='Gi0/0')
        row2 = _clean_bw_row(ip='192.0.2.1', iface='Gi0/0')
        _, data = self._post({'rows': [row1, row2]})
        codes = [f['code'] for f in data['findings']]
        self.assertIn('BW_DUPLICATE_INTERFACE', codes)

    def test_validate_does_not_write_to_db(self):
        before = len(storage.list_bandwidth())
        self._post({'rows': [_clean_bw_row(ip='192.0.2.88')]})
        after = len(storage.list_bandwidth())
        self.assertEqual(before, after)

    def test_orphaned_bw_absent_when_device_exists(self):
        storage.upsert_device(_clean_device(ip='192.0.2.77', name='LiveDevice'))
        _, data = self._post({'rows': [_clean_bw_row(ip='192.0.2.77')]})
        codes = [f['code'] for f in data['findings']]
        self.assertNotIn('BW_ORPHANED', codes,
                         'BW row matching a live DB device should not be flagged as orphaned')


# ---------------------------------------------------------------------------
# Subnet validate-import tests
# ---------------------------------------------------------------------------

class TestValidateImportSubnets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._srv = _TestClient()
        cls.client = cls._srv.client

    @classmethod
    def tearDownClass(cls):
        cls._srv.stop()

    def _post(self, payload):
        return self._srv.post('/api/subnets/validate-import', payload)

    def test_returns_200_with_findings_key(self):
        status, data = self._post({'subnets': [_clean_subnet()]})
        self.assertEqual(status, 200)
        self.assertIn('findings', data)

    def test_findings_is_list(self):
        _, data = self._post({'subnets': []})
        self.assertIsInstance(data['findings'], list)

    def test_missing_key_returns_400(self):
        status, _ = self._post({'rows': []})
        self.assertEqual(status, 400)

    def test_clean_subnet_produces_no_findings(self):
        _, data = self._post({'subnets': [_clean_subnet()]})
        self.assertEqual(data['findings'], [])

    def test_invalid_cidr_produces_finding(self):
        _, data = self._post({'subnets': [{'CIDR': 'not-a-cidr', 'Description': 'Bad'}]})
        codes = [f['code'] for f in data['findings']]
        self.assertIn('SUBNET_INVALID_CIDR', codes)

    def test_duplicate_cidr_produces_finding(self):
        s1 = _clean_subnet(cidr='10.0.0.0/8', desc='Net A')
        s2 = {'CIDR': '10.1.2.3/8', 'Description': 'Net B'}
        _, data = self._post({'subnets': [s1, s2]})
        codes = [f['code'] for f in data['findings']]
        self.assertIn('SUBNET_DUPLICATE_CIDR', codes)

    def test_finding_uses_description_field(self):
        bad = {'CIDR': 'bad-cidr', 'Description': 'MySubnetLabel'}
        _, data = self._post({'subnets': [bad]})
        findings = [f for f in data['findings'] if f['code'] == 'SUBNET_INVALID_CIDR']
        self.assertTrue(findings, 'expected SUBNET_INVALID_CIDR finding')
        self.assertIn('MySubnetLabel', findings[0]['message'])

    def test_validate_does_not_write_to_db(self):
        before = len(storage.list_subnets())
        self._post({'subnets': [_clean_subnet(cidr='172.16.0.0/12')]})
        after = len(storage.list_subnets())
        self.assertEqual(before, after)


if __name__ == '__main__':
    unittest.main()
