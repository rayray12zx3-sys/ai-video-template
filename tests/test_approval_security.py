"""Synthetic events; ephemeral keys never leave test memory."""
import base64
import copy
from datetime import datetime, timezone
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import test_i2_validation as fixture
from aivideo.approvals import SignedApprovalVerifier, adopt_approval, approval_bytes
from aivideo.gates import evaluate_gates, _generative_shots
from aivideo.state_engine import StateConflict
from aivideo.validators import validate_project


class ApprovalSecurityTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.I2Tests('test_each_gate_passes_with_minimum_evidence')
        self.f.setUp()
        self.addCleanup(self.f.tmp.cleanup)
        self.key = Ed25519PrivateKey.generate()
        self.verifier = SignedApprovalVerifier({'test-key': ('operator', self.key.public_key().public_bytes_raw())},
                                                audience='synthetic-private-workflow', history_reader=self.f.engine.inspect_history)

    def envelope(self, kind='BRIEF_LOCK', subject='project:brief', **changes):
        before = self.f.engine.read()
        evidence = self.f.evidence(kind, subject)
        evidence.update(id='signed-event', state_revision=before.state_revision + 1)
        payload = dict(audience='synthetic-private-workflow', project_id=before.document['project_id'],
                       actor_id='operator', operator_event_id='event-1', decision='APPROVE',
                       issued_at=datetime.now(timezone.utc).isoformat(), base_state_revision=before.state_revision,
                       base_project_hash=before.project_hash, evidence=evidence)
        payload.update(changes)
        return {'key_id': 'test-key', 'payload': payload,
                'signature': base64.b64encode(self.key.sign(approval_bytes(payload))).decode()}

    def test_human_string_and_throwing_callback_never_pass(self):
        for callback in (None, lambda *args: False, lambda *args: 1,
                         lambda *args: (_ for _ in ()).throw(ValueError())):
            self.assertNotEqual(evaluate_gates(self.f.engine, approval_verifier=callback)['G0']['status'], 'PASS')

    def test_signed_adoption_uses_engine_and_preserves_history(self):
        envelope = self.envelope()
        before = self.f.engine.read()
        result = adopt_approval(self.f.engine, envelope, self.verifier, transaction_id='adopt-event')
        self.assertEqual(result.state_revision, before.state_revision + 1)
        self.assertEqual(len(self.f.engine.inspect_history()), 1)
        expected = copy.deepcopy(before.document)
        expected['state_revision'] += 1
        expected['evidence'].append({**envelope['payload']['evidence'], 'approval_provenance': envelope})
        self.assertEqual(result.document, expected)
        self.assertEqual(evaluate_gates(self.f.engine, approval_verifier=self.verifier)['G0']['status'], 'PASS')
        with self.assertRaises(StateConflict):
            adopt_approval(self.f.engine, envelope, self.verifier, transaction_id='replay')

    def test_generic_transaction_cannot_forge_adoption_event(self):
        from aivideo.state_engine import TransactionRequest
        from aivideo.validators import fingerprint
        envelope = self.envelope()
        before = self.f.engine.read()
        fake = copy.deepcopy(before.document)
        fake['state_revision'] += 1
        # A fake event cannot reserve this base and add its receipt later.
        with self.assertRaises(ValueError):
            self.f.engine.begin_transaction(TransactionRequest(before.state_revision, before.project_hash,
                'fake-adoption', 'operator', 'HUMAN_APPROVAL_ADOPTED'), fake,
                transition_metadata={'operator_event_id': 'event-1', 'approval_payload_hash': fingerprint(envelope['payload'])})
        self.assertEqual(self.f.engine.read(), before)
        self.assertEqual(self.f.engine.inspect_history(), ())

    def test_forgery_identity_audience_and_base_conflicts_are_zero_write(self):
        for field, value in [('actor_id', 'agent'), ('audience', 'another-workflow'),
                             ('project_id', 'another-project'), ('base_project_hash', '0'*64),
                             ('base_state_revision', True), ('decision', 'INFERRED'),
                             ('issued_at', '2999-01-01T00:00:00Z')]:
            before = self.f.engine.project_path.read_bytes(), self.f.engine.events_path.read_bytes()
            with self.assertRaises(StateConflict):
                adopt_approval(self.f.engine, self.envelope(**{field: value}), self.verifier, transaction_id=field)
            self.assertEqual(before, (self.f.engine.project_path.read_bytes(), self.f.engine.events_path.read_bytes()))
        envelope = self.envelope()
        envelope['payload']['evidence']['subject_hash'] = '0'*64
        with self.assertRaises(StateConflict):
            adopt_approval(self.f.engine, envelope, self.verifier, transaction_id='forgery')

    def test_signed_missing_dependency_is_rejected(self):
        envelope = self.envelope('STORYBOARD_APPROVAL', 'project:storyboard')
        envelope['payload']['evidence']['dependency_hashes'] = {}
        envelope['signature'] = base64.b64encode(self.key.sign(approval_bytes(envelope['payload']))).decode()
        with self.assertRaises(StateConflict):
            adopt_approval(self.f.engine, envelope, self.verifier, transaction_id='missing-binding')

    def test_synced_source_requires_signed_source_review_binding(self):
        self.f.doc['assets'][0]['media_type'] = 'VIDEO'
        self.f.doc['shots'][0].update(production_method='COMPOSITE', generation_required=False,
            base_plate_policy='APPROVED_SOURCE', base_plate_asset_id='input',
            lip_sync={'status': 'REQUIRED'}, lip_sync_execution='SOURCE_ALREADY_SYNCHRONIZED')
        self.f.doc['evidence'] = []
        self.f.write_initial()
        self.assertTrue(validate_project(self.f.engine).ok)
        self.assertEqual(_generative_shots(self.f.doc), [])
        gate = evaluate_gates(self.f.engine)['G2']
        self.assertTrue(any(f.get('subject') == 'shot:shot-a' for f in gate['blocking_findings']))
        envelope = self.envelope('SOURCE_SYNC_APPROVAL', 'shot:shot-a')
        with self.assertRaises(StateConflict):
            adopt_approval(self.f.engine, envelope, self.verifier, transaction_id='unbound-source')
        from aivideo.validators import fingerprint
        envelope['payload']['evidence']['dependency_hashes'] = {'asset:input': fingerprint(self.f.doc['assets'][0])}
        envelope['signature'] = base64.b64encode(self.key.sign(approval_bytes(envelope['payload']))).decode()
        result = adopt_approval(self.f.engine, envelope, self.verifier, transaction_id='source-review')
        evidence = result.document['evidence'][-1]
        self.assertTrue(self.verifier(evidence, result))
        no_history = SignedApprovalVerifier(self.verifier.keyring, audience=self.verifier.audience)
        self.assertFalse(no_history(evidence, result))

    def test_no_paid_policy_denies_even_test_approved_preflight(self):
        self.f.doc['execution_policy'] = {'paid_generation': 'FORBIDDEN'}
        self.f.write_initial()
        self.assertEqual(self.f.guard(self.f.request())['decision'], 'DENY')

    def test_composite_and_lipsync_are_guarded_without_project_ids(self):
        for policy in ({'generation_required': True}, {'lip_sync': {'status': 'REQUIRED'}},
                       {'lip_sync': {'status': 'CONDITIONAL'}}):
            shot = dict(id='arbitrary', readiness='REQUIRED', production_method='COMPOSITE', **policy)
            self.assertEqual(_generative_shots({'shots': [shot]}), [shot])
        self.assertEqual(_generative_shots({'shots': [{'id': 'editorial', 'production_method': 'NO_NEW_MEDIA'}]}), [])

    def test_source_bypass_requires_real_approved_video_binding(self):
        self.f.doc['shots'][0].update(production_method='COMPOSITE', generation_required=False,
                                     base_plate_policy='APPROVED_SOURCE', base_plate_asset_id='absent')
        self.f.doc['evidence'] = []
        self.f.write_initial()
        self.assertIn('BASE_PLATE_SOURCE', {f['code'] for f in validate_project(self.f.engine).findings})

    def test_signed_receipt_cannot_be_transplanted_to_another_base(self):
        envelope = self.envelope()
        self.f.doc['next_action'] = 'Different canonical base, same approved subject'
        self.f.write_initial()
        # Generic State Engine insertion must not bypass the approval adoption protocol.
        self.f.commit(lambda doc: doc['evidence'].append({**envelope['payload']['evidence'],
                                                        'approval_provenance': envelope}))
        self.assertNotEqual(evaluate_gates(self.f.engine, approval_verifier=self.verifier)['G0']['status'], 'PASS')

    def test_missing_composite_contract_and_malformed_fields_fail_closed(self):
        from aivideo.guards import guard_action
        for changes in ({'production_method': 'COMPOSITE'}, {'production_method': {}}, {'production_method': []},
                        {'base_plate_policy': {}}, {'base_plate_policy': []}):
            self.f.doc['shots'][0].update(changes)
            self.f.doc['evidence'] = []
            self.f.write_initial()
            self.assertFalse(validate_project(self.f.engine).ok)
            self.assertEqual(evaluate_gates(self.f.engine)['G0']['status'], 'BLOCKED')
            self.assertEqual(guard_action(self.f.engine, self.f.request())['decision'], 'DENY')
        for malformed in ('REQUIRED', {'status': 'REQUIRE'}, {'status': {}}, []):
            self.f.doc['shots'][0].update(production_method='COMPOSITE', generation_required=False,
                                         base_plate_policy='DETERMINISTIC', lip_sync=malformed)
            self.f.write_initial()
            self.assertIn('LIP_SYNC_CONTRACT', {f['code'] for f in validate_project(self.f.engine).findings})
            self.assertEqual(evaluate_gates(self.f.engine)['G0']['status'], 'BLOCKED')
        self.f.doc['shots'][0].pop('lip_sync')
        self.f.doc['shots'][0].pop('base_plate_policy', None)
        self.f.doc['shots'][0]['production_method'] = 'AI_VIDEO'
        for source in (None, {}, []):
            self.f.doc['dependencies'] = [{'target': 'project:brief', 'source': source}]
            self.f.write_initial()
            self.assertEqual(evaluate_gates(self.f.engine)['G0']['status'], 'BLOCKED')
            self.assertEqual(guard_action(self.f.engine, self.f.request())['decision'], 'DENY')


if __name__ == '__main__':
    unittest.main()
