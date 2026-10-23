"""Testes unitários do orquestrador com fixtures sintéticas locais."""
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sonarfuzzy import cli as orquestrar

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'fixtures'


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


class OrquestrarTests(unittest.TestCase):
    def test_plano_fixture_tem_include_requests_e_parametros_deterministicos(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            manifest = orquestrar.make_plan(
                FIXTURES / 'openapi.json', FIXTURES / 'sonar-issues.json',
                FIXTURES / 'links.csv', output, top_k=2,
                budget_minutes=12, seed=77)
            baseline = json.loads((output / 'restler-baseline.json').read_text())
            guided = json.loads((output / 'restler-guided.json').read_text())

        self.assertEqual(manifest['baseline'], ['GET /items/{itemId}', 'POST /items'])
        self.assertEqual(baseline['include_requests'], [
            {'endpoint': '/items/{itemId}', 'methods': ['GET']},
            {'endpoint': '/items', 'methods': ['POST']},
        ])
        self.assertEqual(guided['include_requests'], baseline['include_requests'])
        self.assertEqual(baseline['time_budget'], guided['time_budget'])
        self.assertEqual(baseline['random_seed'], guided['random_seed'])
        self.assertEqual((baseline['time_budget'], baseline['random_seed']), (0.2, 77))

    def test_vinculo_aprovado_invalido_falha(self):
        with tempfile.TemporaryDirectory() as directory:
            links = Path(directory) / 'links.csv'
            spec = Path(directory) / 'openapi.json'
            spec.write_text(json.dumps({'paths': {'/ok': {'get': {}}}}), encoding='utf-8')
            links.write_text('issue_key,method,path,approved,evidence\n'
                             'DEMO-1,GET,/rota-inexistente,yes,prova\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Vínculo aprovado inválido'):
                orquestrar.make_plan(spec,
                                     FIXTURES / 'sonar-issues.json', links,
                                     Path(directory) / 'out', 2, 10, 1)

    def test_resposta_llm_e_validada_e_ordena_candidatos(self):
        candidates = [{'operation': 'GET /a'}, {'operation': 'POST /b'}]
        request_info = {}

        def fake_urlopen(request, timeout):
            request_info['request'] = request
            request_info['timeout'] = timeout
            return Response({'choices': [{'message': {'content':
                '{"ordered_operations":["POST /b"]}'}}]})

        def fake_plan_urlopen(request, timeout):
            request_info['request'] = request
            request_info['timeout'] = timeout
            return Response({'choices': [{'message': {'content':
                '{"ordered_operations":["POST /items"]}'}}]})

        with patch.object(orquestrar, 'urlopen', side_effect=fake_urlopen):
            order, prompt_hash = orquestrar.llm_order(
                'http://llm.test/v1/chat/completions', 'modelo-teste',
                'segredo-teste', candidates, 4)

        self.assertEqual(order, ['POST /b'])
        self.assertEqual(len(prompt_hash), 64)
        self.assertEqual(request_info['timeout'], 4)
        self.assertEqual(request_info['request'].get_header('Authorization'), 'Bearer segredo-teste')
        with patch.object(orquestrar, 'urlopen', side_effect=fake_plan_urlopen):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                spec = root / 'spec.json'
                spec.write_text(json.dumps({'paths': {
                    '/items': {'post': {}}, '/items/{itemId}': {'get': {}, 'delete': {}}
                }}), encoding='utf-8')
                manifest = orquestrar.make_plan(
                    spec, FIXTURES / 'sonar-issues.json', FIXTURES / 'links.csv',
                    root / 'plan', 2, 10, 9,
                    'http://llm.test/v1/chat/completions', 'modelo-teste', 'segredo-teste')
                self.assertNotEqual(manifest['baseline'], manifest['guided'])
                self.assertEqual(manifest['guided'], ['POST /items', 'GET /items/{itemId}'])

        with self.assertRaisesRegex(ValueError, 'inventada ou repetida'):
            with patch.object(orquestrar, 'urlopen', return_value=Response(
                    {'choices': [{'message': {'content':
                     '{"ordered_operations":["GET /inventado"]}'}}]})):
                orquestrar.llm_order('http://llm.test', 'modelo', '', candidates, 3)

    def test_export_sonar_pagina_e_nao_persiste_token(self):
        payloads = [
            {'paging': {'total': 2}, 'issues': [{'key': 'A', 'message': 'um', 'token': 'nao-exportar'}]},
            {'paging': {'total': 2}, 'issues': [{'key': 'B', 'message': 'dois'}]},
        ]
        requests = []

        def fake_urlopen(request, timeout):
            requests.append(request)
            return Response(payloads[len(requests) - 1])

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'export.json'
            with patch.object(orquestrar, 'urlopen', side_effect=fake_urlopen):
                count = orquestrar.export_sonar('http://sonar.test', 'demo', 'segredo',
                                                output, page_size=1)
            saved = output.read_text(encoding='utf-8')
            exported = json.loads(saved)

        self.assertEqual(count, 2)
        self.assertEqual(len(requests), 2)
        self.assertIn('p=1', requests[0].full_url)
        self.assertIn('p=2', requests[1].full_url)
        self.assertEqual(requests[0].get_header('Authorization'), 'Bearer segredo')
        self.assertNotIn('segredo', saved)
        self.assertNotIn('nao-exportar', saved)
        self.assertEqual([issue['key'] for issue in exported['issues']], ['A', 'B'])

    def test_confirmed_exige_bucket_replay_mesma_causa_e_evidencia(self):
        with tempfile.TemporaryDirectory() as directory:
            review = Path(directory) / 'review.csv'
            output = Path(directory) / 'report.json'
            row = {field: '' for field in orquestrar.REVIEW_FIELDS}
            row.update(issue_key='DEMO-1', verdict='confirmed', same_root_cause='yes',
                       runtime_oracle='HTTP 500', restler_bug_bucket='500',
                       replay_file='replay.txt', evidence='Reproduzido')
            with review.open('w', encoding='utf-8', newline='') as target:
                writer = csv.DictWriter(target, fieldnames=orquestrar.REVIEW_FIELDS)
                writer.writeheader()
                writer.writerow(row)
            report = orquestrar.review_report(review, output)
            self.assertEqual(report['counts']['confirmed'], 1)

            for field in ('same_root_cause', 'runtime_oracle', 'restler_bug_bucket', 'replay_file', 'evidence'):
                invalid = dict(row, **{field: ''})
                with review.open('w', encoding='utf-8', newline='') as target:
                    writer = csv.DictWriter(target, fieldnames=orquestrar.REVIEW_FIELDS)
                    writer.writeheader()
                    writer.writerow(invalid)
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'Confirmação sem oráculo'):
                    orquestrar.review_report(review, output)


if __name__ == '__main__':
    unittest.main()
