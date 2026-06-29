"""
Tests for core.validator — inventory-level validation engine.

Run from the repository root:
    python3 -m unittest tests/logic/test_validation.py
    python3 -m unittest discover tests/logic/

Each test class covers one validation rule or one structural contract.
Module-level fixture helpers build minimal device/bandwidth/subnet dicts
so individual tests stay readable.

Conventions
-----------
- Tests that expect *no findings* assert an empty list or assertNotIn.
- Tests that expect findings assert the exact ``code`` and ``severity``;
  never the exact ``message`` text (messages are operator-facing prose
  and may be rephrased without breaking contracts).
- Category values ARE asserted: they form part of the public contract
  because the frontend and future integrations may filter on them.
- All IP addresses use 192.0.2.x (TEST-NET-1, RFC 5737).
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from core.validator import validate_inventory


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _device(ip='192.0.2.1', name='Router1', region='us-east',
             snmp_user='admin', auth_proto='SHA', auth_key='authpass123',
             priv_proto='AES', priv_key='privpass123',
             config_type=None):
    """Return a minimal device dict that passes all validation rules."""
    d = {
        'IP': ip,
        'Device': name,
        'Collector Region': region,
        'snmpUser': snmp_user,
        'authProtocol': auth_proto,
        'authKey': auth_key,
        'privProtocol': priv_proto,
        'privKey': priv_key,
    }
    if config_type:
        d['Config Type'] = config_type
    return d


def _bw_row(ip='192.0.2.1', interface='GigabitEthernet0/0', bw='1 Gbps'):
    return {'IP': ip, 'Interface': interface, 'Allocated BW': bw}


def _subnet(cidr='192.0.2.0/24', name='Test Net'):
    return {'CIDR': cidr, 'Name': name}


def _codes(findings):
    return [f['code'] for f in findings]


def _by_code(findings, code):
    return [f for f in findings if f['code'] == code]


def _one(findings, code):
    """Return the single finding with the given code; fail if not exactly one."""
    matches = _by_code(findings, code)
    assert len(matches) == 1, f"Expected 1 finding for {code}, got {len(matches)}: {matches}"
    return matches[0]


# ---------------------------------------------------------------------------
# Baseline: clean inventory
# ---------------------------------------------------------------------------

class TestCleanInventory(unittest.TestCase):

    def test_all_valid_returns_empty(self):
        devices = [_device('192.0.2.1', 'R1'), _device('192.0.2.2', 'R2')]
        bandwidth = [_bw_row('192.0.2.1')]
        subnets = [_subnet('192.0.2.0/24')]
        self.assertEqual(validate_inventory(devices, bandwidth, subnets, []), [])

    def test_empty_inventory_returns_empty(self):
        self.assertEqual(validate_inventory([], [], [], []), [])

    def test_no_bandwidth_no_subnets(self):
        self.assertEqual(validate_inventory([_device()], [], [], []), [])


# ---------------------------------------------------------------------------
# DEVICE_NO_IP
# ---------------------------------------------------------------------------

class TestDeviceNoIp(unittest.TestCase):

    def test_blank_ip_triggers(self):
        findings = validate_inventory([_device(ip='')], [], [], [])
        self.assertIn('DEVICE_NO_IP', _codes(findings))

    def test_whitespace_ip_triggers(self):
        findings = validate_inventory([_device(ip='   ')], [], [], [])
        self.assertIn('DEVICE_NO_IP', _codes(findings))

    def test_severity_is_error(self):
        f = _one(validate_inventory([_device(ip='')], [], [], []), 'DEVICE_NO_IP')
        self.assertEqual(f['severity'], 'error')

    def test_category_is_generation(self):
        f = _one(validate_inventory([_device(ip='')], [], [], []), 'DEVICE_NO_IP')
        self.assertEqual(f['category'], 'generation')

    def test_multiple_devices_single_finding(self):
        devices = [_device(ip='', name='A'), _device(ip='', name='B')]
        self.assertEqual(_codes(validate_inventory(devices, [], [], [])).count('DEVICE_NO_IP'), 1)

    def test_valid_ip_does_not_trigger(self):
        self.assertNotIn('DEVICE_NO_IP', _codes(validate_inventory([_device()], [], [], [])))


# ---------------------------------------------------------------------------
# DEVICE_INVALID_IP
# ---------------------------------------------------------------------------

class TestDeviceInvalidIp(unittest.TestCase):

    def _findings(self, ip):
        return validate_inventory([_device(ip=ip)], [], [], [])

    def test_hostname_string_triggers(self):
        self.assertIn('DEVICE_INVALID_IP', _codes(self._findings('router.example.com')))

    def test_partial_octet_triggers(self):
        self.assertIn('DEVICE_INVALID_IP', _codes(self._findings('10.0.0')))

    def test_out_of_range_octet_triggers(self):
        self.assertIn('DEVICE_INVALID_IP', _codes(self._findings('999.0.0.1')))

    def test_severity_is_error(self):
        f = _one(self._findings('bad'), 'DEVICE_INVALID_IP')
        self.assertEqual(f['severity'], 'error')

    def test_category_is_network(self):
        f = _one(self._findings('bad'), 'DEVICE_INVALID_IP')
        self.assertEqual(f['category'], 'network')

    def test_multiple_invalid_single_finding(self):
        devices = [_device(ip='bad1', name='A'), _device(ip='bad2', name='B')]
        self.assertEqual(_codes(validate_inventory(devices, [], [], [])).count('DEVICE_INVALID_IP'), 1)

    def test_valid_ipv4_does_not_trigger(self):
        self.assertNotIn('DEVICE_INVALID_IP', _codes(validate_inventory([_device('192.0.2.1')], [], [], [])))

    def test_valid_ipv6_does_not_trigger(self):
        self.assertNotIn('DEVICE_INVALID_IP', _codes(validate_inventory([_device(ip='::1')], [], [], [])))

    def test_blank_ip_does_not_trigger_this_code(self):
        # Blank IPs produce DEVICE_NO_IP, not DEVICE_INVALID_IP.
        findings = validate_inventory([_device(ip='')], [], [], [])
        self.assertNotIn('DEVICE_INVALID_IP', _codes(findings))


# ---------------------------------------------------------------------------
# DEVICE_DUPLICATE_IP
# ---------------------------------------------------------------------------

class TestDeviceDuplicateIp(unittest.TestCase):

    def test_two_devices_same_ip(self):
        devices = [_device('192.0.2.1', 'R1'), _device('192.0.2.1', 'R2')]
        self.assertIn('DEVICE_DUPLICATE_IP', _codes(validate_inventory(devices, [], [], [])))

    def test_severity_is_warning(self):
        devices = [_device('192.0.2.1', 'R1'), _device('192.0.2.1', 'R2')]
        f = _one(validate_inventory(devices, [], [], []), 'DEVICE_DUPLICATE_IP')
        self.assertEqual(f['severity'], 'warning')

    def test_category_is_inventory(self):
        devices = [_device('192.0.2.1', 'R1'), _device('192.0.2.1', 'R2')]
        f = _one(validate_inventory(devices, [], [], []), 'DEVICE_DUPLICATE_IP')
        self.assertEqual(f['category'], 'inventory')

    def test_three_devices_same_ip_single_finding(self):
        devices = [_device('192.0.2.1', 'R1'),
                   _device('192.0.2.1', 'R2'),
                   _device('192.0.2.1', 'R3')]
        self.assertEqual(_codes(validate_inventory(devices, [], [], [])).count('DEVICE_DUPLICATE_IP'), 1)

    def test_two_independent_duplicate_pairs_single_finding(self):
        devices = [
            _device('192.0.2.1', 'R1'), _device('192.0.2.1', 'R2'),
            _device('192.0.2.5', 'S1'), _device('192.0.2.5', 'S2'),
        ]
        self.assertEqual(_codes(validate_inventory(devices, [], [], [])).count('DEVICE_DUPLICATE_IP'), 1)

    def test_unique_ips_do_not_trigger(self):
        devices = [_device('192.0.2.1', 'R1'), _device('192.0.2.2', 'R2')]
        self.assertNotIn('DEVICE_DUPLICATE_IP', _codes(validate_inventory(devices, [], [], [])))

    def test_duplicate_device_still_checked_for_other_rules(self):
        # A duplicate device that also lacks a region should produce both codes.
        devices = [
            _device('192.0.2.1', 'R1', region='us-east'),
            _device('192.0.2.1', 'R2', region=''),
        ]
        codes = _codes(validate_inventory(devices, [], [], []))
        self.assertIn('DEVICE_DUPLICATE_IP', codes)
        self.assertIn('DEVICE_NO_REGION', codes)

    def test_invalid_ip_not_considered_for_duplicate(self):
        # Two devices with the same invalid IP should not produce DUPLICATE_IP —
        # each is caught by DEVICE_INVALID_IP instead.
        devices = [_device(ip='bad', name='A'), _device(ip='bad', name='B')]
        self.assertNotIn('DEVICE_DUPLICATE_IP', _codes(validate_inventory(devices, [], [], [])))


# ---------------------------------------------------------------------------
# DEVICE_NO_REGION
# ---------------------------------------------------------------------------

class TestDeviceNoRegion(unittest.TestCase):

    def test_blank_region_triggers(self):
        self.assertIn('DEVICE_NO_REGION', _codes(validate_inventory([_device(region='')], [], [], [])))

    def test_whitespace_region_triggers(self):
        self.assertIn('DEVICE_NO_REGION', _codes(validate_inventory([_device(region='   ')], [], [], [])))

    def test_severity_is_error(self):
        f = _one(validate_inventory([_device(region='')], [], [], []), 'DEVICE_NO_REGION')
        self.assertEqual(f['severity'], 'error')

    def test_category_is_generation(self):
        f = _one(validate_inventory([_device(region='')], [], [], []), 'DEVICE_NO_REGION')
        self.assertEqual(f['category'], 'generation')

    def test_multiple_no_region_single_finding(self):
        devices = [_device('192.0.2.1', region=''), _device('192.0.2.2', region='')]
        self.assertEqual(_codes(validate_inventory(devices, [], [], [])).count('DEVICE_NO_REGION'), 1)

    def test_device_with_region_does_not_trigger(self):
        self.assertNotIn('DEVICE_NO_REGION', _codes(validate_inventory([_device(region='us-east')], [], [], [])))

    def test_device_with_no_ip_not_flagged_for_no_region(self):
        # A device with no IP produces DEVICE_NO_IP only; DEVICE_NO_REGION
        # must not also fire because the IP check already renders the device
        # unactionable for region purposes.
        devices = [_device(ip='', region='')]
        codes = _codes(validate_inventory(devices, [], [], []))
        self.assertIn('DEVICE_NO_IP', codes)
        self.assertNotIn('DEVICE_NO_REGION', codes)

    def test_no_region_does_not_produce_missing_creds(self):
        # Credentials are irrelevant for devices excluded from generation.
        devices = [_device(region='', snmp_user='', auth_key='', priv_key='')]
        codes = _codes(validate_inventory(devices, [], [], []))
        self.assertIn('DEVICE_NO_REGION', codes)
        self.assertNotIn('DEVICE_MISSING_CREDS', codes)


# ---------------------------------------------------------------------------
# DEVICE_MISSING_CREDS
# ---------------------------------------------------------------------------

class TestDeviceMissingCreds(unittest.TestCase):

    def test_missing_snmp_user(self):
        self.assertIn('DEVICE_MISSING_CREDS',
                      _codes(validate_inventory([_device(snmp_user='')], [], [], [])))

    def test_missing_auth_key(self):
        self.assertIn('DEVICE_MISSING_CREDS',
                      _codes(validate_inventory([_device(auth_key='')], [], [], [])))

    def test_missing_priv_key(self):
        self.assertIn('DEVICE_MISSING_CREDS',
                      _codes(validate_inventory([_device(priv_key='')], [], [], [])))

    def test_severity_is_warning(self):
        f = _one(validate_inventory([_device(snmp_user='')], [], [], []), 'DEVICE_MISSING_CREDS')
        self.assertEqual(f['severity'], 'warning')

    def test_category_is_snmp(self):
        f = _one(validate_inventory([_device(snmp_user='')], [], [], []), 'DEVICE_MISSING_CREDS')
        self.assertEqual(f['category'], 'snmp')

    def test_icmp_config_type_exempt(self):
        findings = validate_inventory(
            [_device(snmp_user='', auth_key='', priv_key='', config_type='icmp')],
            [], [], [])
        self.assertNotIn('DEVICE_MISSING_CREDS', _codes(findings))

    def test_full_creds_does_not_trigger(self):
        self.assertNotIn('DEVICE_MISSING_CREDS',
                         _codes(validate_inventory([_device()], [], [], [])))

    def test_multiple_missing_single_finding(self):
        devices = [_device('192.0.2.1', snmp_user=''), _device('192.0.2.2', snmp_user='')]
        self.assertEqual(
            _codes(validate_inventory(devices, [], [], [])).count('DEVICE_MISSING_CREDS'), 1)


# ---------------------------------------------------------------------------
# DEVICE_NO_HOSTNAME  (new in Phase 2)
# ---------------------------------------------------------------------------

class TestDeviceNoHostname(unittest.TestCase):

    def test_blank_name_triggers(self):
        findings = validate_inventory([_device(name='')], [], [], [])
        self.assertIn('DEVICE_NO_HOSTNAME', _codes(findings))

    def test_whitespace_name_triggers(self):
        findings = validate_inventory([_device(name='   ')], [], [], [])
        self.assertIn('DEVICE_NO_HOSTNAME', _codes(findings))

    def test_severity_is_warning(self):
        f = _one(validate_inventory([_device(name='')], [], [], []), 'DEVICE_NO_HOSTNAME')
        self.assertEqual(f['severity'], 'warning')

    def test_category_is_inventory(self):
        f = _one(validate_inventory([_device(name='')], [], [], []), 'DEVICE_NO_HOSTNAME')
        self.assertEqual(f['category'], 'inventory')

    def test_device_with_name_does_not_trigger(self):
        self.assertNotIn('DEVICE_NO_HOSTNAME',
                         _codes(validate_inventory([_device(name='Router1')], [], [], [])))

    def test_multiple_unnamed_single_finding(self):
        devices = [_device('192.0.2.1', name=''), _device('192.0.2.2', name='')]
        self.assertEqual(
            _codes(validate_inventory(devices, [], [], [])).count('DEVICE_NO_HOSTNAME'), 1)

    def test_message_contains_ip_as_context(self):
        # When a device has no name, the IP should appear in the message so the
        # operator can locate the row.
        f = _one(validate_inventory([_device('192.0.2.1', name='')], [], [], []),
                 'DEVICE_NO_HOSTNAME')
        self.assertIn('192.0.2.1', f['message'])

    def test_no_hostname_and_no_ip_message_contains_placeholder(self):
        # Device with neither a name nor an IP; message must not crash and must
        # include some placeholder text rather than a blank identifier.
        f = _one(validate_inventory([_device(ip='', name='')], [], [], []),
                 'DEVICE_NO_HOSTNAME')
        self.assertIn('no IP', f['message'])


# ---------------------------------------------------------------------------
# DEVICE_DUPLICATE_HOSTNAME  (new in Phase 2)
# ---------------------------------------------------------------------------

class TestDeviceDuplicateHostname(unittest.TestCase):

    def test_two_devices_same_name(self):
        devices = [_device('192.0.2.1', 'Router1'), _device('192.0.2.2', 'Router1')]
        self.assertIn('DEVICE_DUPLICATE_HOSTNAME',
                      _codes(validate_inventory(devices, [], [], [])))

    def test_severity_is_warning(self):
        devices = [_device('192.0.2.1', 'Router1'), _device('192.0.2.2', 'Router1')]
        f = _one(validate_inventory(devices, [], [], []), 'DEVICE_DUPLICATE_HOSTNAME')
        self.assertEqual(f['severity'], 'warning')

    def test_category_is_inventory(self):
        devices = [_device('192.0.2.1', 'Router1'), _device('192.0.2.2', 'Router1')]
        f = _one(validate_inventory(devices, [], [], []), 'DEVICE_DUPLICATE_HOSTNAME')
        self.assertEqual(f['category'], 'inventory')

    def test_three_devices_same_name_single_finding(self):
        devices = [_device('192.0.2.1', 'R'), _device('192.0.2.2', 'R'),
                   _device('192.0.2.3', 'R')]
        self.assertEqual(
            _codes(validate_inventory(devices, [], [], [])).count('DEVICE_DUPLICATE_HOSTNAME'), 1)

    def test_two_duplicate_name_pairs_single_finding(self):
        devices = [
            _device('192.0.2.1', 'Alpha'), _device('192.0.2.2', 'Alpha'),
            _device('192.0.2.3', 'Beta'),  _device('192.0.2.4', 'Beta'),
        ]
        self.assertEqual(
            _codes(validate_inventory(devices, [], [], [])).count('DEVICE_DUPLICATE_HOSTNAME'), 1)

    def test_unique_names_do_not_trigger(self):
        devices = [_device('192.0.2.1', 'R1'), _device('192.0.2.2', 'R2')]
        self.assertNotIn('DEVICE_DUPLICATE_HOSTNAME',
                         _codes(validate_inventory(devices, [], [], [])))

    def test_blank_names_not_counted_as_duplicates(self):
        # Two devices with blank names should produce DEVICE_NO_HOSTNAME,
        # not DEVICE_DUPLICATE_HOSTNAME.
        devices = [_device('192.0.2.1', ''), _device('192.0.2.2', '')]
        codes = _codes(validate_inventory(devices, [], [], []))
        self.assertIn('DEVICE_NO_HOSTNAME', codes)
        self.assertNotIn('DEVICE_DUPLICATE_HOSTNAME', codes)

    def test_message_contains_duplicate_hostname(self):
        devices = [_device('192.0.2.1', 'CoreSwitch'), _device('192.0.2.2', 'CoreSwitch')]
        f = _one(validate_inventory(devices, [], [], []), 'DEVICE_DUPLICATE_HOSTNAME')
        self.assertIn('CoreSwitch', f['message'])


# ---------------------------------------------------------------------------
# BW_ORPHANED
# ---------------------------------------------------------------------------

class TestBwOrphaned(unittest.TestCase):

    def test_bandwidth_ip_with_no_device(self):
        findings = validate_inventory([_device('192.0.2.1')], [_bw_row('192.0.2.99')], [], [])
        self.assertIn('BW_ORPHANED', _codes(findings))

    def test_severity_is_warning(self):
        f = _one(validate_inventory([], [_bw_row('192.0.2.1')], [], []), 'BW_ORPHANED')
        self.assertEqual(f['severity'], 'warning')

    def test_category_is_inventory(self):
        f = _one(validate_inventory([], [_bw_row('192.0.2.1')], [], []), 'BW_ORPHANED')
        self.assertEqual(f['category'], 'inventory')

    def test_multiple_rows_same_orphan_single_finding(self):
        bandwidth = [_bw_row('192.0.2.99'), _bw_row('192.0.2.99', 'Gi0/1')]
        self.assertEqual(_codes(validate_inventory([], bandwidth, [], [])).count('BW_ORPHANED'), 1)

    def test_multiple_distinct_orphan_ips_single_finding(self):
        bandwidth = [_bw_row('192.0.2.91'), _bw_row('192.0.2.92')]
        self.assertEqual(_codes(validate_inventory([], bandwidth, [], [])).count('BW_ORPHANED'), 1)

    def test_matching_device_does_not_trigger(self):
        findings = validate_inventory([_device('192.0.2.1')], [_bw_row('192.0.2.1')], [], [])
        self.assertNotIn('BW_ORPHANED', _codes(findings))

    def test_empty_bandwidth_does_not_trigger(self):
        self.assertNotIn('BW_ORPHANED', _codes(validate_inventory([_device()], [], [], [])))

    def test_row_with_blank_ip_ignored(self):
        findings = validate_inventory([], [{'IP': '', 'Interface': 'Gi0/0'}], [], [])
        self.assertNotIn('BW_ORPHANED', _codes(findings))

    def test_device_with_invalid_ip_not_counted_as_match(self):
        # An invalid device IP must not absorb bandwidth rows at the same address.
        devices = [_device('not-an-ip')]
        bandwidth = [_bw_row('not-an-ip')]
        codes = _codes(validate_inventory(devices, bandwidth, [], []))
        self.assertIn('DEVICE_INVALID_IP', codes)
        self.assertIn('BW_ORPHANED', codes)


# ---------------------------------------------------------------------------
# BW_DUPLICATE_INTERFACE  (new in Phase 2)
# ---------------------------------------------------------------------------

class TestBwDuplicateInterface(unittest.TestCase):

    def test_same_ip_and_interface_twice(self):
        bandwidth = [_bw_row('192.0.2.1', 'Gi0/0'), _bw_row('192.0.2.1', 'Gi0/0')]
        self.assertIn('BW_DUPLICATE_INTERFACE',
                      _codes(validate_inventory([], bandwidth, [], [])))

    def test_severity_is_warning(self):
        bandwidth = [_bw_row('192.0.2.1', 'Gi0/0'), _bw_row('192.0.2.1', 'Gi0/0')]
        f = _one(validate_inventory([], bandwidth, [], []), 'BW_DUPLICATE_INTERFACE')
        self.assertEqual(f['severity'], 'warning')

    def test_category_is_inventory(self):
        bandwidth = [_bw_row('192.0.2.1', 'Gi0/0'), _bw_row('192.0.2.1', 'Gi0/0')]
        f = _one(validate_inventory([], bandwidth, [], []), 'BW_DUPLICATE_INTERFACE')
        self.assertEqual(f['category'], 'inventory')

    def test_same_ip_different_interfaces_do_not_trigger(self):
        bandwidth = [_bw_row('192.0.2.1', 'Gi0/0'), _bw_row('192.0.2.1', 'Gi0/1')]
        self.assertNotIn('BW_DUPLICATE_INTERFACE',
                         _codes(validate_inventory([], bandwidth, [], [])))

    def test_same_interface_different_ips_do_not_trigger(self):
        bandwidth = [_bw_row('192.0.2.1', 'Gi0/0'), _bw_row('192.0.2.2', 'Gi0/0')]
        self.assertNotIn('BW_DUPLICATE_INTERFACE',
                         _codes(validate_inventory([], bandwidth, [], [])))

    def test_multiple_duplicate_pairs_single_finding(self):
        bandwidth = [
            _bw_row('192.0.2.1', 'Gi0/0'), _bw_row('192.0.2.1', 'Gi0/0'),
            _bw_row('192.0.2.2', 'Gi0/1'), _bw_row('192.0.2.2', 'Gi0/1'),
        ]
        self.assertEqual(
            _codes(validate_inventory([], bandwidth, [], [])).count('BW_DUPLICATE_INTERFACE'), 1)

    def test_row_with_blank_interface_ignored(self):
        bandwidth = [{'IP': '192.0.2.1', 'Interface': ''}, {'IP': '192.0.2.1', 'Interface': ''}]
        self.assertNotIn('BW_DUPLICATE_INTERFACE',
                         _codes(validate_inventory([], bandwidth, [], [])))

    def test_row_with_blank_ip_ignored(self):
        bandwidth = [{'IP': '', 'Interface': 'Gi0/0'}, {'IP': '', 'Interface': 'Gi0/0'}]
        self.assertNotIn('BW_DUPLICATE_INTERFACE',
                         _codes(validate_inventory([], bandwidth, [], [])))

    def test_message_contains_ip_and_interface(self):
        bandwidth = [_bw_row('192.0.2.1', 'Gi0/0'), _bw_row('192.0.2.1', 'Gi0/0')]
        f = _one(validate_inventory([], bandwidth, [], []), 'BW_DUPLICATE_INTERFACE')
        self.assertIn('192.0.2.1', f['message'])
        self.assertIn('Gi0/0', f['message'])


# ---------------------------------------------------------------------------
# SUBNET_INVALID_CIDR
# ---------------------------------------------------------------------------

class TestSubnetInvalidCidr(unittest.TestCase):

    def test_garbage_cidr_triggers(self):
        self.assertIn('SUBNET_INVALID_CIDR',
                      _codes(validate_inventory([], [], [_subnet('not-a-cidr')], [])))

    def test_out_of_range_octet_triggers(self):
        self.assertIn('SUBNET_INVALID_CIDR',
                      _codes(validate_inventory([], [], [_subnet('300.0.0.0/24')], [])))

    def test_severity_is_error(self):
        f = _one(validate_inventory([], [], [_subnet('bad')], []), 'SUBNET_INVALID_CIDR')
        self.assertEqual(f['severity'], 'error')

    def test_category_is_network(self):
        f = _one(validate_inventory([], [], [_subnet('bad')], []), 'SUBNET_INVALID_CIDR')
        self.assertEqual(f['category'], 'network')

    def test_multiple_invalid_single_finding(self):
        subnets = [_subnet('bad1', 'A'), _subnet('bad2', 'B')]
        self.assertEqual(
            _codes(validate_inventory([], [], subnets, [])).count('SUBNET_INVALID_CIDR'), 1)

    def test_valid_cidr_does_not_trigger(self):
        self.assertNotIn('SUBNET_INVALID_CIDR',
                         _codes(validate_inventory([], [], [_subnet('192.0.2.0/24')], [])))

    def test_slash_32_host_route_is_valid(self):
        self.assertNotIn('SUBNET_INVALID_CIDR',
                         _codes(validate_inventory([], [], [_subnet('192.0.2.1/32')], [])))

    def test_non_strict_cidr_host_bits_set_is_valid(self):
        # ip_network(strict=False) accepts host bits set; so should the validator.
        self.assertNotIn('SUBNET_INVALID_CIDR',
                         _codes(validate_inventory([], [], [_subnet('192.0.2.1/24')], [])))

    def test_bare_ip_without_prefix_is_valid(self):
        # Python treats '192.0.2.0' as a /32 — not an error.
        self.assertNotIn('SUBNET_INVALID_CIDR',
                         _codes(validate_inventory([], [], [_subnet('192.0.2.0')], [])))

    def test_blank_cidr_ignored(self):
        self.assertNotIn('SUBNET_INVALID_CIDR',
                         _codes(validate_inventory([], [], [{'CIDR': '', 'Name': 'X'}], [])))


# ---------------------------------------------------------------------------
# SUBNET_DUPLICATE_CIDR  (new in Phase 2)
# ---------------------------------------------------------------------------

class TestSubnetDuplicateCidr(unittest.TestCase):

    def test_same_cidr_twice(self):
        subnets = [_subnet('192.0.2.0/24', 'A'), _subnet('192.0.2.0/24', 'B')]
        self.assertIn('SUBNET_DUPLICATE_CIDR',
                      _codes(validate_inventory([], [], subnets, [])))

    def test_severity_is_warning(self):
        subnets = [_subnet('192.0.2.0/24', 'A'), _subnet('192.0.2.0/24', 'B')]
        f = _one(validate_inventory([], [], subnets, []), 'SUBNET_DUPLICATE_CIDR')
        self.assertEqual(f['severity'], 'warning')

    def test_category_is_network(self):
        subnets = [_subnet('192.0.2.0/24', 'A'), _subnet('192.0.2.0/24', 'B')]
        f = _one(validate_inventory([], [], subnets, []), 'SUBNET_DUPLICATE_CIDR')
        self.assertEqual(f['category'], 'network')

    def test_different_cidrs_do_not_trigger(self):
        subnets = [_subnet('192.0.2.0/24'), _subnet('192.0.3.0/24')]
        self.assertNotIn('SUBNET_DUPLICATE_CIDR',
                         _codes(validate_inventory([], [], subnets, [])))

    def test_host_bits_set_normalised_before_comparison(self):
        # 192.0.2.1/24 normalises to 192.0.2.0/24 — same as 192.0.2.0/24.
        subnets = [_subnet('192.0.2.0/24', 'A'), _subnet('192.0.2.1/24', 'B')]
        self.assertIn('SUBNET_DUPLICATE_CIDR',
                      _codes(validate_inventory([], [], subnets, [])))

    def test_three_subnets_same_cidr_single_finding(self):
        subnets = [_subnet('192.0.2.0/24', 'A'), _subnet('192.0.2.0/24', 'B'),
                   _subnet('192.0.2.0/24', 'C')]
        self.assertEqual(
            _codes(validate_inventory([], [], subnets, [])).count('SUBNET_DUPLICATE_CIDR'), 1)

    def test_two_duplicate_pairs_single_finding(self):
        subnets = [
            _subnet('192.0.2.0/24', 'A'), _subnet('192.0.2.0/24', 'B'),
            _subnet('192.0.3.0/24', 'C'), _subnet('192.0.3.0/24', 'D'),
        ]
        self.assertEqual(
            _codes(validate_inventory([], [], subnets, [])).count('SUBNET_DUPLICATE_CIDR'), 1)

    def test_invalid_cidr_not_considered_for_duplicate(self):
        # Two subnets with the same invalid CIDR should produce SUBNET_INVALID_CIDR
        # only, not SUBNET_DUPLICATE_CIDR.
        subnets = [_subnet('bad', 'A'), _subnet('bad', 'B')]
        codes = _codes(validate_inventory([], [], subnets, []))
        self.assertIn('SUBNET_INVALID_CIDR', codes)
        self.assertNotIn('SUBNET_DUPLICATE_CIDR', codes)

    def test_blank_cidr_ignored(self):
        subnets = [{'CIDR': '', 'Name': 'A'}, {'CIDR': '', 'Name': 'B'}]
        self.assertNotIn('SUBNET_DUPLICATE_CIDR',
                         _codes(validate_inventory([], [], subnets, [])))


# ---------------------------------------------------------------------------
# Output sort order
# ---------------------------------------------------------------------------

class TestSortOrder(unittest.TestCase):
    """Findings must be sorted errors-first, then warnings; within the same
    severity, sorted alphabetically by message for deterministic output."""

    def _mixed_inventory(self):
        devices = [
            _device(ip=''),                          # error: DEVICE_NO_IP
            _device('192.0.2.1', region=''),         # error: DEVICE_NO_REGION
            _device('192.0.2.2', snmp_user=''),      # warning: DEVICE_MISSING_CREDS
            _device('192.0.2.3', 'R3'),
            _device('192.0.2.3', 'R3b'),             # warning: DEVICE_DUPLICATE_IP
        ]
        return validate_inventory(devices, [], [], [])

    def test_errors_precede_warnings(self):
        findings = self._mixed_inventory()
        severities = [f['severity'] for f in findings]
        # Find the last 'error' and the first 'warning'.
        last_error_idx = max((i for i, s in enumerate(severities) if s == 'error'), default=-1)
        first_warn_idx = min((i for i, s in enumerate(severities) if s == 'warning'), default=len(severities))
        self.assertLess(last_error_idx, first_warn_idx,
                        f"An error appeared after a warning: {severities}")

    def test_within_errors_sorted_by_message(self):
        findings = self._mixed_inventory()
        error_msgs = [f['message'] for f in findings if f['severity'] == 'error']
        self.assertEqual(error_msgs, sorted(error_msgs))

    def test_within_warnings_sorted_by_message(self):
        findings = self._mixed_inventory()
        warn_msgs = [f['message'] for f in findings if f['severity'] == 'warning']
        self.assertEqual(warn_msgs, sorted(warn_msgs))

    def test_sort_is_deterministic_across_calls(self):
        devices = [_device('192.0.2.1', 'R1'), _device('192.0.2.2', region=''),
                   _device('192.0.2.3', snmp_user='')]
        result_a = validate_inventory(devices, [], [], [])
        result_b = validate_inventory(devices, [], [], [])
        self.assertEqual(result_a, result_b)

    def test_clean_inventory_returns_empty_list(self):
        self.assertEqual(validate_inventory([_device()], [_bw_row()], [_subnet()], []), [])


# ---------------------------------------------------------------------------
# Finding structure contract (all fields, all valid values)
# ---------------------------------------------------------------------------

class TestFindingStructure(unittest.TestCase):
    """Every finding must conform to the documented four-field schema."""

    VALID_SEVERITIES = {'error', 'warning'}
    VALID_CATEGORIES = {'inventory', 'snmp', 'network', 'generation'}
    ALL_CODES = {
        'DEVICE_NO_IP', 'DEVICE_INVALID_IP', 'DEVICE_DUPLICATE_IP',
        'DEVICE_NO_REGION', 'DEVICE_MISSING_CREDS',
        'DEVICE_NO_HOSTNAME', 'DEVICE_DUPLICATE_HOSTNAME',
        'BW_ORPHANED', 'BW_DUPLICATE_INTERFACE',
        'SUBNET_INVALID_CIDR', 'SUBNET_DUPLICATE_CIDR',
    }

    def _all_findings(self):
        """Construct an inventory that triggers every known rule."""
        devices = [
            _device(ip='', name='NoIp'),                           # DEVICE_NO_IP
            _device(ip='bad', name='BadIp'),                       # DEVICE_INVALID_IP
            _device('192.0.2.1', 'Dup1'),
            _device('192.0.2.1', 'Dup2'),                          # DEVICE_DUPLICATE_IP
            _device('192.0.2.2', region=''),                       # DEVICE_NO_REGION
            _device('192.0.2.3', snmp_user=''),                    # DEVICE_MISSING_CREDS
            _device('192.0.2.4', name=''),                         # DEVICE_NO_HOSTNAME
            _device('192.0.2.5', 'SameName'),
            _device('192.0.2.6', 'SameName'),                      # DEVICE_DUPLICATE_HOSTNAME
        ]
        bandwidth = [
            _bw_row('192.0.2.99'),                                  # BW_ORPHANED
            _bw_row('192.0.2.5', 'Gi0/0'),
            _bw_row('192.0.2.5', 'Gi0/0'),                         # BW_DUPLICATE_INTERFACE
        ]
        subnets = [
            _subnet('not-a-cidr', 'Bad'),                           # SUBNET_INVALID_CIDR
            _subnet('192.0.2.0/24', 'Dup A'),
            _subnet('192.0.2.0/24', 'Dup B'),                      # SUBNET_DUPLICATE_CIDR
        ]
        return validate_inventory(devices, bandwidth, subnets, [])

    def test_every_finding_has_four_required_keys(self):
        for finding in self._all_findings():
            with self.subTest(finding=finding):
                self.assertIn('code', finding)
                self.assertIn('severity', finding)
                self.assertIn('category', finding)
                self.assertIn('message', finding)

    def test_severity_is_valid(self):
        for finding in self._all_findings():
            with self.subTest(code=finding['code']):
                self.assertIn(finding['severity'], self.VALID_SEVERITIES)

    def test_category_is_valid(self):
        for finding in self._all_findings():
            with self.subTest(code=finding['code']):
                self.assertIn(finding['category'], self.VALID_CATEGORIES)

    def test_code_is_non_empty_string(self):
        for finding in self._all_findings():
            with self.subTest(finding=finding):
                self.assertIsInstance(finding['code'], str)
                self.assertTrue(finding['code'])

    def test_message_is_non_empty_string(self):
        for finding in self._all_findings():
            with self.subTest(code=finding['code']):
                self.assertIsInstance(finding['message'], str)
                self.assertTrue(finding['message'])

    def test_all_eleven_codes_present(self):
        codes = set(_codes(self._all_findings()))
        self.assertEqual(codes, self.ALL_CODES)

    def test_no_extra_keys_in_finding(self):
        expected_keys = {'code', 'severity', 'category', 'message'}
        for finding in self._all_findings():
            with self.subTest(code=finding['code']):
                self.assertEqual(set(finding.keys()), expected_keys)


# ---------------------------------------------------------------------------
# Category assignments — explicit contract per rule
# ---------------------------------------------------------------------------

class TestCategoryAssignments(unittest.TestCase):
    """Category values form part of the public API.  Assert them explicitly
    so any accidental change is immediately visible in the test output."""

    def _cat(self, code, findings):
        matches = _by_code(findings, code)
        self.assertEqual(len(matches), 1, f"Expected 1 finding for {code}")
        return matches[0]['category']

    def test_device_no_ip_is_generation(self):
        f = validate_inventory([_device(ip='')], [], [], [])
        self.assertEqual(self._cat('DEVICE_NO_IP', f), 'generation')

    def test_device_invalid_ip_is_network(self):
        f = validate_inventory([_device(ip='bad')], [], [], [])
        self.assertEqual(self._cat('DEVICE_INVALID_IP', f), 'network')

    def test_device_duplicate_ip_is_inventory(self):
        devices = [_device('192.0.2.1', 'A'), _device('192.0.2.1', 'B')]
        f = validate_inventory(devices, [], [], [])
        self.assertEqual(self._cat('DEVICE_DUPLICATE_IP', f), 'inventory')

    def test_device_no_region_is_generation(self):
        f = validate_inventory([_device(region='')], [], [], [])
        self.assertEqual(self._cat('DEVICE_NO_REGION', f), 'generation')

    def test_device_missing_creds_is_snmp(self):
        f = validate_inventory([_device(snmp_user='')], [], [], [])
        self.assertEqual(self._cat('DEVICE_MISSING_CREDS', f), 'snmp')

    def test_device_no_hostname_is_inventory(self):
        f = validate_inventory([_device(name='')], [], [], [])
        self.assertEqual(self._cat('DEVICE_NO_HOSTNAME', f), 'inventory')

    def test_device_duplicate_hostname_is_inventory(self):
        devices = [_device('192.0.2.1', 'R'), _device('192.0.2.2', 'R')]
        f = validate_inventory(devices, [], [], [])
        self.assertEqual(self._cat('DEVICE_DUPLICATE_HOSTNAME', f), 'inventory')

    def test_bw_orphaned_is_inventory(self):
        f = validate_inventory([], [_bw_row('192.0.2.99')], [], [])
        self.assertEqual(self._cat('BW_ORPHANED', f), 'inventory')

    def test_bw_duplicate_interface_is_inventory(self):
        bw = [_bw_row('192.0.2.1', 'Gi0/0'), _bw_row('192.0.2.1', 'Gi0/0')]
        f = validate_inventory([], bw, [], [])
        self.assertEqual(self._cat('BW_DUPLICATE_INTERFACE', f), 'inventory')

    def test_subnet_invalid_cidr_is_network(self):
        f = validate_inventory([], [], [_subnet('bad')], [])
        self.assertEqual(self._cat('SUBNET_INVALID_CIDR', f), 'network')

    def test_subnet_duplicate_cidr_is_network(self):
        subnets = [_subnet('192.0.2.0/24', 'A'), _subnet('192.0.2.0/24', 'B')]
        f = validate_inventory([], [], subnets, [])
        self.assertEqual(self._cat('SUBNET_DUPLICATE_CIDR', f), 'network')


if __name__ == '__main__':
    unittest.main()
