#!/usr/bin/env python3
"""Cria experimentos auditáveis SonarQube -> OpenAPI -> RESTler.

Sem dependências obrigatórias; PyYAML é opcional para OpenAPI em YAML.
Não executa RESTler nem infere causalidade automaticamente.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

METHODS = {'get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'trace'}
APPROVED = {'sim', 'yes', 'true', '1', 'aprovado'}
REVIEW_FIELDS = ['issue_key', 'method', 'path', 'sonar_rule', 'sonar_component',
                 'sonar_line', 'runtime_oracle', 'restler_bug_bucket', 'replay_file',
                 'same_root_cause', 'verdict', 'evidence', 'notes']
VERDICTS = {'confirmed', 'unrelated_runtime_failure', 'not_reproduced', 'inconclusive'}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def read_data(path: Path) -> object:
    if path.suffix.lower() in {'.yaml', '.yml'}:
        try:
            import yaml
        except ImportError as exc:
            raise ValueError('OpenAPI YAML requer PyYAML; use JSON ou instale PyYAML') from exc
        return yaml.safe_load(path.read_text(encoding='utf-8'))
    return json.loads(path.read_text(encoding='utf-8'))


def operations(spec: dict) -> dict[str, dict]:
    if not isinstance(spec, dict) or not isinstance(spec.get('paths'), dict):
        raise ValueError('Especificação OpenAPI sem objeto paths')
    result = {}
    for path, item in spec['paths'].items():
        if not isinstance(path, str) or not path.startswith('/') or not isinstance(item, dict):
            continue
        for method, definition in item.items():
            if method.lower() not in METHODS or not isinstance(definition, dict):
                continue
            label = f'{method.upper()} {path}'
            result[label] = {'method': method.upper(), 'path': path,
                             'operation_id': definition.get('operationId', ''),
                             'summary': str(definition.get('summary', ''))[:300],
                             'description': str(definition.get('description', ''))[:300]}
    if not result:
        raise ValueError('Nenhuma operação HTTP encontrada em paths')
    return result


def sonar_issues(data: object) -> dict[str, dict]:
    rows = data.get('issues') if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError('JSON Sonar sem lista issues')
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not row.get('key'):
            raise ValueError('Issue Sonar sem key')
        key = str(row['key'])
        if key in result:
            raise ValueError(f'Issue Sonar duplicada: {key}')
        result[key] = row
    return result


def export_sonar(base_url: str, project: str, token: str, output: Path,
                 page_size: int = 100, max_pages: int = 100) -> int:
    if not token or not project or not base_url.startswith(('http://', 'https://')):
        raise ValueError('Informe URL, project key e token SonarQube')
    if not 1 <= page_size <= 500 or max_pages < 1:
        raise ValueError('Paginação inválida')
    all_issues = []
    total = None
    last_batch_size = 0
    for page in range(1, max_pages + 1):
        query = urlencode({'componentKeys': project, 'p': page, 'ps': page_size})
        url = base_url.rstrip('/') + '/api/issues/search?' + query
        request = Request(url, headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json'})
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except HTTPError as exc:
            raise RuntimeError(f'SonarQube respondeu HTTP {exc.code} na página {page}') from exc
        except URLError as exc:
            raise RuntimeError(f'Falha de conexão SonarQube na página {page}: {exc.reason}') from exc
        if not isinstance(payload, dict):
            raise ValueError(f'Resposta SonarQube inválida na página {page}')
        batch = payload.get('issues')
        if not isinstance(batch, list):
            raise ValueError(f'SonarQube não retornou issues na página {page}')
        paging = payload.get('paging', {})
        if isinstance(paging, dict) and isinstance(paging.get('total'), int):
            total = paging['total']
        all_issues.extend(batch)
        last_batch_size = len(batch)
        if (total is not None and len(all_issues) >= total) or len(batch) < page_size:
            break
    if total is not None and len(all_issues) < total:
        raise RuntimeError(f'Exportação incompleta: {len(all_issues)} de {total} issues; aumente --max-pages')
    if total is None and last_batch_size == page_size:
        raise RuntimeError('Exportação possivelmente incompleta: atingiu --max-pages sem total informado')
    if len({r.get('key') for r in all_issues}) != len(all_issues):
        raise ValueError('Paginação Sonar retornou issues repetidas')
    # Somente metadados necessários; sem token e sem código-fonte.
    fields = ('key', 'rule', 'component', 'line', 'textRange', 'type', 'severity',
              'impacts', 'status', 'resolution', 'message')
    slim = [{k: row[k] for k in fields if k in row} for row in all_issues]
    write_json(output, {'project_key': project, 'source_url': base_url.rstrip('/'),
                        'consulted_at_utc': datetime.now(timezone.utc).isoformat(),
                        'total_reported': total, 'issues': slim})
    return len(slim)


def read_links(path: Path, issues: dict, ops: dict) -> dict[str, list[str]]:
    linked = {}
    with path.open(encoding='utf-8-sig', newline='') as source:
        reader = csv.DictReader(source)
        if not {'issue_key', 'method', 'path', 'approved', 'evidence'} <= set(reader.fieldnames or ()):
            raise ValueError('CSV de vínculos requer issue_key,method,path,approved,evidence')
        for line, row in enumerate(reader, 2):
            if row['approved'].strip().lower() not in APPROVED:
                continue
            key = row['issue_key'].strip()
            operation = f"{row['method'].strip().upper()} {row['path'].strip()}"
            if key not in issues or operation not in ops or not row['evidence'].strip():
                raise ValueError(f'Vínculo aprovado inválido na linha {line}: {key} -> {operation}')
            status = str(issues[key].get('status', '')).upper()
            if status in {'CLOSED', 'RESOLVED', 'FALSE_POSITIVE', 'ACCEPTED'} or issues[key].get('resolution'):
                continue
            linked.setdefault(operation, [])
            if key not in linked[operation]:
                linked[operation].append(key)
    return linked


def llm_order(url: str, model: str, api_key: str, candidates: list[dict], timeout: float) -> tuple[list[str], str]:
    if not url.startswith(('http://', 'https://')) or not model:
        raise ValueError('LLM exige --llm-url HTTP(S) e --llm-model')
    prompt = json.dumps({'task': 'Prioritize existing REST API operations for a short RESTler run. '
                                'Return ONLY JSON: {"ordered_operations": ["METHOD /path", ...]}. '
                                'Use each candidate at most once. Do not invent paths or assert bugs.',
                         'candidates': candidates}, ensure_ascii=False, separators=(',', ':'))
    body = {'model': model, 'temperature': 0,
            'messages': [{'role': 'system', 'content': 'You rank candidates, not verify vulnerabilities. Output JSON only.'},
                         {'role': 'user', 'content': prompt}]}
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    request = Request(url, data=json.dumps(body).encode(), headers=headers, method='POST')
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f'LLM respondeu HTTP {exc.code}') from exc
    content = payload['choices'][0]['message']['content']
    data = json.loads(content)
    order = data.get('ordered_operations')
    if not isinstance(order, list) or any(not isinstance(x, str) for x in order):
        raise ValueError('LLM não retornou ordered_operations como lista de strings')
    allowed = {item['operation'] for item in candidates}
    if len(order) != len(set(order)) or not set(order) <= allowed:
        raise ValueError('LLM retornou operação inventada ou repetida')
    return order, hashlib.sha256(prompt.encode()).hexdigest()


def restler_settings(order: list[str], ops: dict, budget_minutes: float, seed: int) -> dict:
    return {'include_requests': [{'endpoint': ops[label]['path'], 'methods': [ops[label]['method']]}
                                 for label in order],
            'time_budget': budget_minutes / 60, 'random_seed': seed,
            'generate_random_seed': False}


def make_plan(spec_path: Path, issues_path: Path, links_path: Path, output: Path,
              top_k: int, budget_minutes: float, seed: int,
              llm_url: str = '', llm_model: str = '', llm_api_key: str = '', llm_timeout: float = 30) -> dict:
    if top_k < 1 or budget_minutes <= 0:
        raise ValueError('top-k e orçamento devem ser positivos')
    ops = operations(read_data(spec_path))
    issues = sonar_issues(read_data(issues_path))
    linked = read_links(links_path, issues, ops)
    if not linked:
        raise ValueError('Nenhum vínculo aprovado; revise links.csv antes de dirigir RESTler')
    baseline = sorted(linked, key=lambda op: (-len(linked[op]), op))
    candidates = [{'operation': op, 'summary': ops[op]['summary'],
                   'description': ops[op]['description'],
                   'issue_count': len(linked[op]),
                   'issues': [{'key': key, 'rule': issues[key].get('rule', ''),
                               'message': str(issues[key].get('message', ''))[:300],
                               'severity': issues[key].get('severity', ''),
                               'type': issues[key].get('type', '')} for key in linked[op][:5]]}
                  for op in baseline]
    guided = baseline.copy()
    llm = None
    if llm_url or llm_model:
        pool = candidates[:50]
        order, prompt_hash = llm_order(llm_url, llm_model, llm_api_key, pool, llm_timeout)
        guided = order + [op for op in baseline if op not in order]
        llm = {'model': llm_model, 'url': llm_url, 'prompt_sha256': prompt_hash,
               'returned_order': order, 'candidate_count': len(pool)}
    count = min(top_k, len(baseline))
    output.mkdir(parents=True, exist_ok=True)
    manifest = {'created_at_utc': datetime.now(timezone.utc).isoformat(),
                'inputs_sha256': {str(path): digest(path) for path in [spec_path, issues_path, links_path]},
                'top_k': count, 'budget_minutes': budget_minutes, 'seed': seed,
                'baseline': baseline[:count], 'guided': guided[:count],
                'candidate_operations': candidates, 'llm': llm,
                'limits': 'Associação aprovada não prova execução; bug bucket não prova mesma causa.'}
    write_json(output / 'plan.json', manifest)
    write_json(output / 'restler-baseline.json', restler_settings(baseline[:count], ops, budget_minutes, seed))
    write_json(output / 'restler-guided.json', restler_settings(guided[:count], ops, budget_minutes, seed))
    with (output / 'review.csv').open('w', encoding='utf-8', newline='') as target:
        writer = csv.DictWriter(target, fieldnames=REVIEW_FIELDS)
        writer.writeheader()
        for op in sorted(set(baseline[:count]) | set(guided[:count])):
            for key in linked[op]:
                issue = issues[key]
                writer.writerow({'issue_key': key, 'method': ops[op]['method'], 'path': ops[op]['path'],
                                 'sonar_rule': issue.get('rule', ''),
                                 'sonar_component': issue.get('component', ''),
                                 'sonar_line': issue.get('line', ''),
                                 'same_root_cause': '', 'verdict': '', 'evidence': ''})
    return manifest


def review_report(path: Path, output: Path) -> dict:
    counts = {key: 0 for key in VERDICTS}
    counts['pending'] = 0
    with path.open(encoding='utf-8-sig', newline='') as source:
        reader = csv.DictReader(source)
        if not set(REVIEW_FIELDS) <= set(reader.fieldnames or ()):
            raise ValueError('review.csv sem colunas esperadas')
        for line, row in enumerate(reader, 2):
            verdict = row['verdict'].strip().lower() or 'pending'
            if verdict not in counts:
                raise ValueError(f'Veredito desconhecido na linha {line}: {verdict}')
            if verdict == 'confirmed' and (row['same_root_cause'].strip().lower() not in APPROVED
                                           or not row['runtime_oracle'].strip()
                                           or not row['restler_bug_bucket'].strip()
                                           or not row['replay_file'].strip()
                                           or not row['evidence'].strip()):
                raise ValueError(f'Confirmação sem oráculo, replay, bug bucket e evidência de mesma causa na linha {line}')
            counts[verdict] += 1
    result = {'review_csv_sha256': digest(path), 'counts': counts,
              'definition': 'confirmed requer replay e confirmação humana da mesma causa; pending não é negativo'}
    write_json(output, result)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    export = sub.add_parser('export-sonar', help='Consulta paginada da API SonarQube')
    export.add_argument('--url', required=True)
    export.add_argument('--project-key', required=True)
    export.add_argument('--token-env', default='SONAR_TOKEN')
    export.add_argument('--output', type=Path, required=True)
    export.add_argument('--page-size', type=int, default=100)
    export.add_argument('--max-pages', type=int, default=100)
    listing = sub.add_parser('list-openapi', help='Lista operações para ajudar a montar links.csv')
    listing.add_argument('--openapi', type=Path, required=True)
    listing.add_argument('--output', type=Path, required=True)
    plan = sub.add_parser('plan', help='Gera baseline e priorização opcional por LLM')
    plan.add_argument('--openapi', type=Path, required=True)
    plan.add_argument('--issues', type=Path, required=True)
    plan.add_argument('--links', type=Path, required=True)
    plan.add_argument('--output', type=Path, required=True)
    plan.add_argument('--top-k', type=int, default=5)
    plan.add_argument('--budget-minutes', type=float, default=10)
    plan.add_argument('--seed', type=int, default=12345)
    plan.add_argument('--llm-url', default='')
    plan.add_argument('--llm-model', default='')
    plan.add_argument('--llm-key-env', default='LLM_API_KEY')
    plan.add_argument('--llm-timeout', type=float, default=30)
    report = sub.add_parser('report', help='Resume a revisão humana dos achados')
    report.add_argument('--review', type=Path, required=True)
    report.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'export-sonar':
            count = export_sonar(args.url, args.project_key, os.environ.get(args.token_env, ''),
                                 args.output, args.page_size, args.max_pages)
            print(f'Exportadas {count} issues para {args.output}')
        elif args.command == 'list-openapi':
            rows = operations(read_data(args.openapi))
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open('w', encoding='utf-8', newline='') as target:
                writer = csv.DictWriter(target, fieldnames=['method', 'path', 'operation_id', 'summary', 'description'])
                writer.writeheader()
                writer.writerows(rows[key] for key in sorted(rows))
            print(f'Listadas {len(rows)} operações em {args.output}')
        elif args.command == 'plan':
            result = make_plan(args.openapi, args.issues, args.links, args.output,
                               args.top_k, args.budget_minutes, args.seed,
                               args.llm_url, args.llm_model, os.environ.get(args.llm_key_env, ''),
                               args.llm_timeout)
            print(f'Plano com {result["top_k"]} operações por braço em {args.output}')
        else:
            result = review_report(args.review, args.output)
            print(json.dumps(result['counts'], ensure_ascii=False))
    except (OSError, ValueError, KeyError, IndexError, RuntimeError, json.JSONDecodeError) as exc:
        print(f'Erro: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
