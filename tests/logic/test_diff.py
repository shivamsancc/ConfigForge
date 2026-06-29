"""
Tests for core.diff — import change preview engine.

Run from the repository root:
    python3 -m unittest tests/logic/test_diff.py
    python3 -m unittest discover tests/logic/

Conventions
-----------
- All IP addresses use 192.0.2.x (TEST-NET-1, RFC 5737) or 198.51.100.x
  (TEST-NET-2) so tests never touch routable space.
- Each test class covers one rule, one scope, or one structural contract.
- Tests assert the exact ``code`` value in diff entries (key, label, changes)
  rather than human-readable messages, which may be rephrased at any time.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from core.diff import diff_import


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _dev(ip='192.0.2.1', name='Router1', region='us-east',
         snmp_user='admin', auth_proto='SHA', auth_key='authpass',
         priv_proto='AES', priv_key='privpass',
         config_type='', remarks='', tags=None):
    return {
        'IP': ip,
        'Device': name,
        'Collector Region': region,
        'snmpUser': snmp_user,
        'authProtocol': auth_proto,
        'authKey': auth_key,
        'privProtocol': priv_proto,
        'privKey': priv_key,
        'Config Type': config_type,
        'Remarks': remarks,
        'tags': tags or {},
    }


def _bw(ip='192.0.2.1', iface='GigabitEthernet0/0', bw='1 Gbps',
        region='', center='', link_type='', desc='', tags=None):
    return {
        'IP': ip,
        'Interface': iface,
        'Allocated BW': bw,
        'Region': region,
        'Center': center,
        'Link Type': link_type,
        'Interface_description': desc,
        'tags': tags or {},
    }


def _subnet(cidr='192.0.2.0/24', description='Test Net', tags=None):
    return {
        'CIDR': cidr,
        'Description': description,
        'tags': tags or {},
    }


def _tag_def(tid, name):
    return {'id': tid, 'name': name, 'scopes': ['devices', 'bandwidth', 'subnets']}


def _codes(diff_result, category):
    """Return set of keys found in diff_result[category]."""
    return {item['key'] for item in diff_result[category]}


# ---------------------------------------------------------------------------
# TestDiffDevicesNew
# ---------------------------------------------------------------------------

class TestDiffDevicesNew(unittest.TestCase):
    """Incoming device not found in existing → appears in new."""

    def test_completely_new_device(self):
        result = diff_import('devices', [_dev(ip='192.0.2.1')], [], 'merge')
        self.assertIn('192.0.2.1', _codes(result, 'new'))
        self.assertEqual(result['unchanged'], 0)
        self.assertEqual(result['modified'], [])

    def test_new_label_uses_hostname_and_ip(self):
        result = diff_import('devices', [_dev(ip='192.0.2.1', name='R1')], [], 'merge')
        self.assertEqual(result['new'][0]['label'], 'R1 (192.0.2.1)')

    def test_new_label_falls_back_to_ip_when_no_hostname(self):
        d = _dev(ip='192.0.2.2', name='')
        result = diff_import('devices', [d], [], 'merge')
        self.assertEqual(result['new'][0]['label'], '192.0.2.2')

    def test_multiple_new_devices(self):
        incoming = [_dev(ip='192.0.2.1'), _dev(ip='192.0.2.2')]
        result = diff_import('devices', incoming, [], 'merge')
        self.assertEqual(len(result['new']), 2)

    def test_no_removed_in_merge_mode_when_new(self):
        existing = [_dev(ip='192.0.2.99')]
        incoming = [_dev(ip='192.0.2.1')]
        result = diff_import('devices', incoming, existing, 'merge')
        self.assertEqual(result['removed'], [])


# ---------------------------------------------------------------------------
# TestDiffDevicesUnchanged
# ---------------------------------------------------------------------------

class TestDiffDevicesUnchanged(unittest.TestCase):
    """Incoming device identical to existing → counted in unchanged."""

    def test_identical_device_is_unchanged(self):
        d = _dev()
        result = diff_import('devices', [d], [d], 'merge')
        self.assertEqual(result['unchanged'], 1)
        self.assertEqual(result['new'], [])
        self.assertEqual(result['modified'], [])

    def test_whitespace_normalised_unchanged(self):
        existing = _dev(ip='192.0.2.1', name='Router1')
        incoming = _dev(ip='192.0.2.1', name='Router1 ')  # trailing space
        result = diff_import('devices', [incoming], [existing], 'merge')
        self.assertEqual(result['unchanged'], 1)

    def test_unchanged_count_accumulates(self):
        devs = [_dev(ip=f'192.0.2.{i}', name=f'R{i}') for i in range(1, 6)]
        result = diff_import('devices', devs, devs, 'merge')
        self.assertEqual(result['unchanged'], 5)


# ---------------------------------------------------------------------------
# TestDiffDevicesModified
# ---------------------------------------------------------------------------

class TestDiffDevicesModified(unittest.TestCase):
    """Incoming device matches existing IP but has changed fields."""

    def _mod(self, **kwargs):
        ex = _dev()
        inc = _dev(**kwargs)
        return diff_import('devices', [inc], [ex], 'merge')

    def _field_names(self, result):
        return {ch['field'] for ch in result['modified'][0]['changes']}

    def test_hostname_change_detected(self):
        result = self._mod(name='NewName')
        self.assertEqual(len(result['modified']), 1)
        names = self._field_names(result)
        self.assertIn('Device', names)

    def test_region_change_detected(self):
        result = self._mod(region='eu-west')
        self.assertIn('Collector Region', self._field_names(result))

    def test_config_type_change_detected(self):
        result = self._mod(config_type='ICMP')
        self.assertIn('Config Type', self._field_names(result))

    def test_snmp_user_change_detected(self):
        result = self._mod(snmp_user='newuser')
        self.assertIn('snmpUser', self._field_names(result))

    def test_auth_proto_change_detected(self):
        result = self._mod(auth_proto='MD5')
        self.assertIn('authProtocol', self._field_names(result))

    def test_priv_proto_change_detected(self):
        result = self._mod(priv_proto='DES')
        self.assertIn('privProtocol', self._field_names(result))

    def test_modified_label_uses_incoming_record(self):
        ex = _dev(name='OldName')
        inc = _dev(name='NewName')
        result = diff_import('devices', [inc], [ex], 'merge')
        self.assertIn('NewName', result['modified'][0]['label'])

    def test_old_and_new_values_present_for_plain_field(self):
        ex = _dev(name='OldName')
        inc = _dev(name='NewName')
        result = diff_import('devices', [inc], [ex], 'merge')
        change = next(c for c in result['modified'][0]['changes'] if c['field'] == 'Device')
        self.assertEqual(change['old'], 'OldName')
        self.assertEqual(change['new'], 'NewName')

    def test_only_changed_fields_appear_in_changes(self):
        ex = _dev(name='A', region='us-east')
        inc = _dev(name='B', region='us-east')   # only Device changed
        result = diff_import('devices', [inc], [ex], 'merge')
        names = self._field_names(result)
        self.assertIn('Device', names)
        self.assertNotIn('Collector Region', names)


# ---------------------------------------------------------------------------
# TestDiffDevicesCredentials
# ---------------------------------------------------------------------------

class TestDiffDevicesCredentials(unittest.TestCase):
    """Credential fields (authKey, privKey) are masked in the diff payload."""

    def _cred_changes(self, field, old_val, new_val):
        ex = _dev(**{field: old_val})
        inc = _dev(**{field: new_val})
        result = diff_import('devices', [inc], [ex], 'merge')
        return result['modified'][0]['changes'] if result['modified'] else []

    def test_auth_key_change_emits_credential_flag(self):
        changes = self._cred_changes('auth_key', 'oldpass', 'newpass')
        cred_changes = [c for c in changes if c.get('credential')]
        self.assertTrue(any(c['field'] == 'authKey' for c in cred_changes))

    def test_priv_key_change_emits_credential_flag(self):
        changes = self._cred_changes('priv_key', 'oldpass', 'newpass')
        cred_changes = [c for c in changes if c.get('credential')]
        self.assertTrue(any(c['field'] == 'privKey' for c in cred_changes))

    def test_auth_key_change_has_no_old_or_new_values(self):
        changes = self._cred_changes('auth_key', 'oldpass', 'newpass')
        auth_change = next(c for c in changes if c['field'] == 'authKey')
        self.assertNotIn('old', auth_change)
        self.assertNotIn('new', auth_change)

    def test_unchanged_auth_key_produces_no_change_entry(self):
        d = _dev(auth_key='samepass')
        result = diff_import('devices', [d], [d], 'merge')
        self.assertEqual(result['unchanged'], 1)
        self.assertEqual(result['modified'], [])


# ---------------------------------------------------------------------------
# TestDiffDevicesRemoved
# ---------------------------------------------------------------------------

class TestDiffDevicesRemoved(unittest.TestCase):
    """Replace mode: existing devices not in incoming appear as removed."""

    def test_removed_in_replace_mode(self):
        existing = [_dev(ip='192.0.2.1'), _dev(ip='192.0.2.2')]
        incoming = [_dev(ip='192.0.2.1')]
        result = diff_import('devices', incoming, existing, 'replace')
        self.assertIn('192.0.2.2', _codes(result, 'removed'))

    def test_no_removed_in_merge_mode(self):
        existing = [_dev(ip='192.0.2.1'), _dev(ip='192.0.2.2')]
        incoming = [_dev(ip='192.0.2.1')]
        result = diff_import('devices', incoming, existing, 'merge')
        self.assertEqual(result['removed'], [])

    def test_removed_label_from_existing_record(self):
        existing = [_dev(ip='192.0.2.99', name='Gone')]
        result = diff_import('devices', [], existing, 'replace')
        self.assertIn('Gone', result['removed'][0]['label'])


# ---------------------------------------------------------------------------
# TestDiffDevicesDuplicateKeyHandling
# ---------------------------------------------------------------------------

class TestDiffDevicesDuplicateKeyHandling(unittest.TestCase):
    """When incoming has duplicate IPs, first occurrence wins."""

    def test_duplicate_ip_first_wins(self):
        d1 = _dev(ip='192.0.2.1', name='First')
        d2 = _dev(ip='192.0.2.1', name='Second')
        result = diff_import('devices', [d1, d2], [], 'merge')
        # Only one new entry despite two incoming records.
        self.assertEqual(len(result['new']), 1)
        self.assertIn('First', result['new'][0]['label'])


# ---------------------------------------------------------------------------
# TestDiffDevicesTags
# ---------------------------------------------------------------------------

class TestDiffDevicesTags(unittest.TestCase):
    """Tag changes appear in modified.changes with the tag name as field."""

    TAG_ID = 'tag-uuid-001'
    TAG_DEFS = [_tag_def('tag-uuid-001', 'Device Class')]

    def test_tag_value_change_detected(self):
        ex = _dev(tags={self.TAG_ID: 'Switch'})
        inc = _dev(tags={self.TAG_ID: 'Router'})
        result = diff_import('devices', [inc], [ex], 'merge', self.TAG_DEFS)
        fields = [c['field'] for c in result['modified'][0]['changes']]
        self.assertIn('Device Class', fields)

    def test_tag_change_shows_old_and_new(self):
        ex = _dev(tags={self.TAG_ID: 'Switch'})
        inc = _dev(tags={self.TAG_ID: 'Router'})
        result = diff_import('devices', [inc], [ex], 'merge', self.TAG_DEFS)
        change = next(c for c in result['modified'][0]['changes'] if c['field'] == 'Device Class')
        self.assertEqual(change['old'], 'Switch')
        self.assertEqual(change['new'], 'Router')

    def test_identical_tags_produce_no_change(self):
        d = _dev(tags={self.TAG_ID: 'Switch'})
        result = diff_import('devices', [d], [d], 'merge', self.TAG_DEFS)
        self.assertEqual(result['unchanged'], 1)

    def test_tag_added_detected(self):
        ex = _dev(tags={})
        inc = _dev(tags={self.TAG_ID: 'Router'})
        result = diff_import('devices', [inc], [ex], 'merge', self.TAG_DEFS)
        fields = [c['field'] for c in result['modified'][0]['changes']]
        self.assertIn('Device Class', fields)

    def test_tag_removed_detected(self):
        ex = _dev(tags={self.TAG_ID: 'Switch'})
        inc = _dev(tags={})
        result = diff_import('devices', [inc], [ex], 'merge', self.TAG_DEFS)
        fields = [c['field'] for c in result['modified'][0]['changes']]
        self.assertIn('Device Class', fields)

    def test_unknown_tag_id_falls_back_to_id(self):
        """If tagDefs don't cover the ID, fall back to displaying the raw ID."""
        ex = _dev(tags={'unknown-id': 'A'})
        inc = _dev(tags={'unknown-id': 'B'})
        result = diff_import('devices', [inc], [ex], 'merge', [])
        fields = [c['field'] for c in result['modified'][0]['changes']]
        self.assertIn('unknown-id', fields)


# ---------------------------------------------------------------------------
# TestDiffBandwidth
# ---------------------------------------------------------------------------

class TestDiffBandwidth(unittest.TestCase):
    """Bandwidth diff: keyed by (IP, Interface)."""

    def test_new_bw_row(self):
        result = diff_import('bandwidth', [_bw()], [], 'merge')
        self.assertEqual(len(result['new']), 1)

    def test_bw_key_is_ip_pipe_interface(self):
        result = diff_import('bandwidth', [_bw(ip='192.0.2.5', iface='Gi0/1')], [], 'merge')
        self.assertEqual(result['new'][0]['key'], '192.0.2.5|Gi0/1')

    def test_bw_label_format(self):
        result = diff_import('bandwidth', [_bw(ip='192.0.2.5', iface='Gi0/1')], [], 'merge')
        self.assertEqual(result['new'][0]['label'], '192.0.2.5 / Gi0/1')

    def test_unchanged_bw_row(self):
        b = _bw()
        result = diff_import('bandwidth', [b], [b], 'merge')
        self.assertEqual(result['unchanged'], 1)

    def test_bw_change_detected(self):
        ex = _bw(bw='500 Mbps')
        inc = _bw(bw='1 Gbps')
        result = diff_import('bandwidth', [inc], [ex], 'merge')
        self.assertEqual(len(result['modified']), 1)
        fields = [c['field'] for c in result['modified'][0]['changes']]
        self.assertIn('Allocated BW', fields)

    def test_bw_removed_in_replace_mode(self):
        existing = [_bw(ip='192.0.2.1', iface='Gi0/0'), _bw(ip='192.0.2.2', iface='Gi0/1')]
        incoming = [_bw(ip='192.0.2.1', iface='Gi0/0')]
        result = diff_import('bandwidth', incoming, existing, 'replace')
        self.assertEqual(len(result['removed']), 1)
        self.assertEqual(result['removed'][0]['key'], '192.0.2.2|Gi0/1')

    def test_bw_rows_with_blank_ip_skipped(self):
        b = _bw(ip='', iface='Gi0/0')
        result = diff_import('bandwidth', [b], [], 'merge')
        # Blank-key records are silently dropped (no key → not indexable).
        self.assertEqual(len(result['new']), 0)

    def test_bw_duplicate_key_first_wins(self):
        b1 = _bw(ip='192.0.2.1', iface='Gi0/0', bw='500 Mbps')
        b2 = _bw(ip='192.0.2.1', iface='Gi0/0', bw='1 Gbps')
        result = diff_import('bandwidth', [b1, b2], [], 'merge')
        self.assertEqual(len(result['new']), 1)


# ---------------------------------------------------------------------------
# TestDiffSubnets
# ---------------------------------------------------------------------------

class TestDiffSubnets(unittest.TestCase):
    """Subnet diff: keyed by normalised CIDR."""

    def test_new_subnet(self):
        result = diff_import('subnets', [_subnet()], [], 'merge')
        self.assertEqual(len(result['new']), 1)

    def test_cidr_normalised_host_bits(self):
        """192.0.2.5/24 and 192.0.2.0/24 normalise to the same key."""
        ex = _subnet(cidr='192.0.2.0/24', description='Net A')
        inc = _subnet(cidr='192.0.2.5/24', description='Net A')  # host bits set
        result = diff_import('subnets', [inc], [ex], 'merge')
        self.assertEqual(result['unchanged'], 1)

    def test_description_change_detected(self):
        ex = _subnet(description='Old Name')
        inc = _subnet(description='New Name')
        result = diff_import('subnets', [inc], [ex], 'merge')
        self.assertEqual(len(result['modified']), 1)
        fields = [c['field'] for c in result['modified'][0]['changes']]
        self.assertIn('Description', fields)

    def test_subnet_label_includes_description(self):
        result = diff_import('subnets', [_subnet(cidr='10.0.0.0/8', description='HQ')], [], 'merge')
        self.assertIn('HQ', result['new'][0]['label'])
        self.assertIn('10.0.0.0/8', result['new'][0]['label'])

    def test_subnet_label_fallback_to_cidr(self):
        result = diff_import('subnets', [_subnet(cidr='10.0.0.0/8', description='')], [], 'merge')
        self.assertEqual(result['new'][0]['label'], '10.0.0.0/8')

    def test_invalid_cidr_kept_as_raw_key(self):
        """Invalid CIDRs are handled by the validator; diff uses raw string as key."""
        result = diff_import('subnets', [_subnet(cidr='bad-cidr')], [], 'merge')
        self.assertEqual(result['new'][0]['key'], 'bad-cidr')

    def test_subnet_removed_in_replace_mode(self):
        existing = [_subnet(cidr='10.0.0.0/8'), _subnet(cidr='10.1.0.0/16')]
        incoming = [_subnet(cidr='10.0.0.0/8')]
        result = diff_import('subnets', incoming, existing, 'replace')
        self.assertEqual(len(result['removed']), 1)

    def test_subnet_no_removed_in_merge_mode(self):
        existing = [_subnet(cidr='10.0.0.0/8'), _subnet(cidr='10.1.0.0/16')]
        incoming = [_subnet(cidr='10.0.0.0/8')]
        result = diff_import('subnets', incoming, existing, 'merge')
        self.assertEqual(result['removed'], [])


# ---------------------------------------------------------------------------
# TestDiffStructure
# ---------------------------------------------------------------------------

class TestDiffStructure(unittest.TestCase):
    """The diff result always has all four expected keys."""

    def test_result_has_all_keys(self):
        result = diff_import('devices', [], [], 'merge')
        for key in ('new', 'modified', 'unchanged', 'removed'):
            self.assertIn(key, result, f"missing key: {key!r}")

    def test_new_and_removed_are_lists(self):
        result = diff_import('devices', [], [], 'merge')
        self.assertIsInstance(result['new'], list)
        self.assertIsInstance(result['removed'], list)

    def test_modified_is_list(self):
        result = diff_import('devices', [], [], 'merge')
        self.assertIsInstance(result['modified'], list)

    def test_unchanged_is_int(self):
        result = diff_import('devices', [], [], 'merge')
        self.assertIsInstance(result['unchanged'], int)

    def test_modified_item_has_key_label_changes(self):
        ex = _dev(name='Old')
        inc = _dev(name='New')
        result = diff_import('devices', [inc], [ex], 'merge')
        item = result['modified'][0]
        self.assertIn('key', item)
        self.assertIn('label', item)
        self.assertIn('changes', item)

    def test_plain_change_has_field_old_new(self):
        ex = _dev(name='Old')
        inc = _dev(name='New')
        result = diff_import('devices', [inc], [ex], 'merge')
        change = next(c for c in result['modified'][0]['changes'] if c['field'] == 'Device')
        self.assertIn('old', change)
        self.assertIn('new', change)

    def test_credential_change_has_field_and_credential_flag(self):
        ex = _dev(auth_key='oldpass')
        inc = _dev(auth_key='newpass')
        result = diff_import('devices', [inc], [ex], 'merge')
        cred_change = next(c for c in result['modified'][0]['changes']
                           if c.get('credential'))
        self.assertIn('field', cred_change)
        self.assertTrue(cred_change['credential'])

    def test_unknown_scope_raises(self):
        with self.assertRaises(ValueError):
            diff_import('unknown_scope', [], [], 'merge')

    def test_empty_inputs_all_zeros(self):
        result = diff_import('devices', [], [], 'merge')
        self.assertEqual(result['new'], [])
        self.assertEqual(result['modified'], [])
        self.assertEqual(result['unchanged'], 0)
        self.assertEqual(result['removed'], [])


if __name__ == '__main__':
    unittest.main()
