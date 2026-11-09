r"""docfig: 문서(HTML)에 직접 쓰는 인라인 SVG 그림 도구. 외부 라이브러리·이미지·스크립트 없이 오프라인·폐쇄망에서도 열린다.

쓰는 법 (그림 만드는 임시 스크립트에서):
    import sys; sys.path.insert(0, 'skills/docfig/scripts')  # 또는 현재 프로젝트의 figlib.py가 있는 경로
    from figlib import Flow, matrix, figure, Doc

    f = Flow(1000, 300, '그림이 말하는 한 문장(스크린리더용)', 'dep')   # 'dep' = 문서 안에서 겹치지 않는 짧은 id
    f.legend(10, 22, [('step', '단계'), ('gap', '아직 없음')])
    f.box(10, 60, 140, 56, ['check', '사전점검'], 'step')
    f.arrow([(150, 88), (198, 88)], '통과하면', 174, 80)
    svg = f.render()

    d = Doc('docs/deploy-guide.html')
    d.insert_after('<h2 id="s5">5. 배포</h2>\n', figure(svg, '그림 설명 한두 문장', 'fig-deploy'))
    # 문서가 판 번호('버전 x.y')와 '변경 이력' 표·archive/ 보관을 쓰는 경우에만 선택 호출:
    # d.bump('그림 추가: 배포 순서 흐름도', date='2026-11-09')
    d.save()

명령줄:
    python skills/docfig/scripts/figlib.py check <html>...       그림·링크 점검 (svg 안 script 없음, figcaption·aria-label 있음, 깨진 링크)
    python skills/docfig/scripts/figlib.py shot <html> [폴더]     그림마다 밝은·어두운 화면 스크린샷(PNG). 글자 겹침·잘림을 눈으로 본다
"""
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.parse

# ---------------------------------------------------------------- 색 (문서 CSS와 무관하게 그림 전용 변수)
LIGHT = {'text': '#1F2328', 'muted': '#5F6670', 'line': '#D3D7DC', 'panel': '#FFFFFF', 'fill': '#F3F5F7',
         'accent': '#1F5F8B', 'accent-bg': '#E8F1F7', 'warn': '#8A5A00', 'warn-bg': '#FDF3DC',
         'no': '#9B2C2C', 'no-bg': '#FBE9E9', 'ok': '#1D6B45', 'ok-bg': '#E5F3EC'}
DARK = {'text': '#E8E9EB', 'muted': '#A3A9B1', 'line': '#3A3F46', 'panel': '#1F2226', 'fill': '#262A30',
        'accent': '#8CC3E8', 'accent-bg': '#1E3442', 'warn': '#F0C674', 'warn-bg': '#3B2F14',
        'no': '#F0A0A0', 'no-bg': '#3E2020', 'ok': '#86D0A8', 'ok-bg': '#183428'}
MARK = '/* docfig */'


def _vars(d):
    return ';'.join(f'--fg-{k}:{v}' for k, v in d.items())


FIG_CSS = (MARK + '\n:root{' + _vars(LIGHT) + '}\n'
           '@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){' + _vars(DARK) + '}}\n'
           ':root[data-theme="dark"]{' + _vars(DARK) + '}\n'
           'figure.fig{background:var(--fg-panel);color:var(--fg-text);border:1px solid var(--fg-line);border-radius:10px;padding:12px 14px;margin:14px 0;overflow-x:auto}\n'
           'figure.fig svg{display:block;width:100%;height:auto;margin:0 auto}\n'
           'figure.fig figcaption{font-size:13px;color:var(--fg-muted);margin-top:8px;line-height:1.6}\n')

V = lambda k: f'var(--fg-{k})'  # noqa: E731


def esc(t):
    return str(t).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def text_width(t, size=12.0):
    """한글·전각은 넓게, 영문·숫자는 좁게 어림한 글자 폭(px). 상자 폭·범례 간격 계산용."""
    return sum((0.95 if ord(ch) > 0x2000 else 0.56) * size for ch in str(t))


BOX = {
    'item': f'fill:{V("panel")};stroke:{V("line")};stroke-width:1.5',          # 표·파일·구성요소
    'pii': f'fill:{V("panel")};stroke:{V("warn")};stroke-width:2.5',           # 개인정보·민감정보 있음
    'step': f'fill:{V("accent-bg")};stroke:{V("accent")};stroke-width:1.5',   # 단계·명령·처리
    'llm': f'fill:{V("accent-bg")};stroke:{V("accent")};stroke-width:3',      # LLM·모델을 부르는 곳
    'person': f'fill:{V("warn-bg")};stroke:{V("warn")};stroke-width:1.5',     # 사람이 하는 일
    'ok': f'fill:{V("ok-bg")};stroke:{V("ok")};stroke-width:1.5',             # 완료·통과
    'gap': f'fill:{V("no-bg")};stroke:{V("no")};stroke-width:1.5;stroke-dasharray:6 4',  # 아직 없음·막힘
    'group': f'fill:none;stroke:{V("line")};stroke-width:1.5',                 # 묶음 테두리
    'band': f'fill:{V("fill")};stroke:{V("line")};stroke-width:1',             # 배경 띠
}


class Flow:
    """흐름도·구조도. 좌표는 viewBox 기준(px). 격자에 맞춰 x·y를 고르고, 화살표에는 뜻을 적는다."""

    def __init__(self, w, h, label, mid, x0=0, y0=0):
        self.w, self.h, self.aria, self.mid = w, h, label, mid
        self.x0, self.y0 = x0, y0
        self.parts = []

    def add(self, s):
        self.parts.append(s)

    def text(self, x, y, t, size=12.5, weight=400, anchor='middle', color='text'):
        self.add(f'<text x="{x}" y="{y}" text-anchor="{anchor}" style="fill:{V(color)};font-size:{size}px;font-weight:{weight}">{esc(t)}</text>')

    def box(self, x, y, w, h, lines, kind='item', sub=None):
        """lines[0]은 굵게, 나머지는 작게. sub는 맨 위 회색 작은 글씨(층·위치 이름)."""
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" style="{BOX[kind]}"/>')
        rows = ([('sub', sub)] if sub else []) + [('main' if i == 0 else 'rest', t) for i, t in enumerate(lines)]
        lh = 16
        top = y + h / 2 - (len(rows) - 1) * lh / 2 + 4
        cx = x + w / 2
        for i, (role, t) in enumerate(rows):
            if role == 'sub':
                self.text(cx, top + i * lh, t, size=11, color='muted')
            elif role == 'main':
                self.text(cx, top + i * lh, t, size=12.5, weight=600, color='no' if kind == 'gap' else 'text')
            else:
                self.text(cx, top + i * lh, t, size=11.5, color='no' if kind == 'gap' else 'muted')

    def label(self, x, y, t, anchor='middle', size=11, color='muted', weight=400):
        self.text(x, y, t, size=size, anchor=anchor, color=color, weight=weight)

    def arrow(self, pts, label=None, lx=None, ly=None, gap=False, anchor='middle', both=False):
        d = ' '.join(f'{x},{y}' for x, y in pts)
        st = f'fill:none;stroke:{V("no")};stroke-width:1.6;stroke-dasharray:6 4' if gap else f'fill:none;stroke:{V("text")};stroke-width:1.4'
        mk = 'g' if gap else 'a'
        start = f' marker-start="url(#{self.mid}{mk})"' if both else ''
        self.add(f'<polyline points="{d}" style="{st}" marker-end="url(#{self.mid}{mk})"{start}/>')
        if label:
            self.text(lx, ly, label, size=11, anchor=anchor, color='no' if gap else 'muted')

    def legend(self, x, y, items):
        """items: [(kind, '설명')] — 같은 모양이 그림에서 여러 번 나올 때만 넣는다."""
        cx = x
        for kind, t in items:
            self.add(f'<rect x="{cx}" y="{y - 11}" width="22" height="14" rx="3" style="{BOX[kind]}"/>')
            self.text(cx + 28, y, t, size=11.5, anchor='start', color='muted')
            cx += 28 + text_width(t, 11.5) + 22

    def render(self):
        m = self.mid
        defs = (f'<defs><marker id="{m}a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                f'<path d="M0,0 L10,5 L0,10 z" style="fill:{V("text")}"/></marker>'
                f'<marker id="{m}g" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                f'<path d="M0,0 L10,5 L0,10 z" style="fill:{V("no")}"/></marker></defs>')
        return (f'<svg viewBox="{self.x0} {self.y0} {self.w} {self.h}" role="img" aria-label="{esc(self.aria)}" '
                f'style="color:{V("text")};font-family:inherit;max-width:{self.w}px;min-width:{min(self.w, 720)}px" xmlns="http://www.w3.org/2000/svg">' + defs + ''.join(self.parts) + '</svg>')


# ---------------------------------------------------------------- 매핑 그림 (가로 × 세로 격자)
CELL = {
    'w': (f'fill:{V("accent-bg")};stroke:{V("accent")};stroke-width:1.5', 'text', 600),    # 씀
    'rw': (f'fill:{V("accent-bg")};stroke:{V("accent")};stroke-width:2.5', 'text', 600),   # 읽고 씀
    'r': (f'fill:{V("panel")};stroke:{V("muted")};stroke-width:1.2', 'muted', 400),        # 읽음
    'c': (f'fill:none;stroke:{V("muted")};stroke-width:1;stroke-dasharray:3 3', 'muted', 400),  # 자리만·빈 표
    'h': (f'fill:{V("warn-bg")};stroke:{V("warn")};stroke-width:1.3', 'warn', 600),        # 사람이 함
    'ok': (f'fill:{V("ok-bg")};stroke:{V("ok")};stroke-width:1.3', 'ok', 600),             # 완료·있음
    'f': (f'fill:{V("no-bg")};stroke:{V("no")};stroke-width:1.3;stroke-dasharray:5 3', 'no', 400),  # 아직 없음
}


def matrix(cols, groups, label, mid, name_w=190, group_w=104, col_w=100, row_h=38, legend=None, top=58):
    """다대다 관계(단계 × 표, 주체 × 저장소, 환경 × 설정 등)를 격자로.
    cols:   [('열 이름', '작은 설명' 또는 '')]
    groups: [('묶음 이름\\n둘째 줄', [('행 이름', '작은 설명', 개인정보여부, {열번호: (칸종류, '칸 글자')})])]
    칸종류: w 씀 · rw 읽고 씀 · r 읽음 · c 자리만 · h 사람이 함 · ok 완료 · f 아직 없음
    legend: [(칸종류, '설명')]"""
    x0 = group_w + name_w
    W = x0 + col_w * len(cols) + 10
    n_rows = sum(len(r) for _, r in groups)
    H = top + 30 + n_rows * row_h + (len(groups) - 1) * 10 + 14
    s = Flow(W, H, label, mid)
    if legend:
        lx = 10
        for kind, t in legend:
            st = CELL[kind][0]
            s.add(f'<rect x="{lx}" y="11" width="26" height="15" rx="4" style="{st}"/>')
            s.text(lx + 32, 23, t, size=11.5, anchor='start', color='muted')
            lx += 32 + text_width(t, 11.5) + 24
    hy = top + 14
    for i, (c, sub) in enumerate(cols):
        cx = x0 + col_w * i + col_w / 2
        s.text(cx, hy - 4, c, size=12.5, weight=600)
        if sub:
            s.text(cx, hy + 11, sub, size=10.5, color='muted')
    y = top + 30
    for g, rows in groups:
        gh = len(rows) * row_h
        s.add(f'<rect x="6" y="{y + 2}" width="{group_w - 12}" height="{gh - 4}" rx="6" style="fill:{V("accent-bg")};stroke:none"/>')
        gl = g.split('\n')
        for k, t in enumerate(gl):
            s.text(group_w / 2, y + gh / 2 + 4 + (k - (len(gl) - 1) / 2) * 14, t, size=11.5, weight=600 if k == 0 else 400, color='text' if k == 0 else 'muted')
        for ri, (name, note, pii, cells) in enumerate(rows):
            ry = y + ri * row_h
            if ri > 0:
                s.add(f'<line x1="{group_w}" y1="{ry}" x2="{W - 6}" y2="{ry}" style="stroke:{V("line")};stroke-width:1"/>')
            if pii:
                s.add(f'<rect x="{group_w}" y="{ry + 6}" width="4" height="{row_h - 12}" rx="2" style="fill:{V("warn")}"/>')
            s.text(group_w + 12, ry + row_h / 2 - (2 if note else -4), name, size=12, weight=600, anchor='start')
            if note:
                s.text(group_w + 12, ry + row_h / 2 + 12, note, size=10.5, anchor='start', color='muted')
            for ci, (kind, t) in cells.items():
                st, tc, fw = CELL[kind]
                cx = x0 + col_w * ci
                s.add(f'<rect x="{cx + 6}" y="{ry + 7}" width="{col_w - 12}" height="{row_h - 14}" rx="5" style="{st}"/>')
                s.add(f'<text x="{cx + col_w / 2}" y="{ry + row_h / 2 + 4}" text-anchor="middle" '
                      f'style="fill:{V(tc)};font-size:{10.5 if text_width(t, 11.5) > col_w - 20 else 11.5}px;font-weight:{fw}">{esc(t)}</text>')
        y += gh + 10
    for i in range(len(cols) + 1):
        x = x0 + col_w * i
        s.add(f'<line x1="{x}" y1="{top}" x2="{x}" y2="{y - 10}" style="stroke:{V("line")};stroke-width:1;stroke-dasharray:2 4"/>')
    return s.render()


def figure(svg, caption, fid):
    """caption: 그림이 보여 주는 것과 읽는 법을 한두 문장(HTML 가능). fid: 문서 안에서 하나뿐인 id."""
    return f'<figure class="fig" id="{fid}">{svg}<figcaption>{caption}</figcaption></figure>\n'


# ---------------------------------------------------------------- 문서 고치기 (삽입·치환·선택적 판 관리)
class Doc:
    def __init__(self, path):
        self.path = path
        raw = io.open(path, encoding='utf-8', newline='').read()
        self.crlf = '\r\n' in raw
        self.html = raw.replace('\r\n', '\n')
        self._css()

    def _css(self):
        if MARK in self.html:
            return
        if '</style>' in self.html:
            i = self.html.index('</style>')
            self.html = self.html[:i] + FIG_CSS + self.html[i:]
        elif '</head>' in self.html:
            i = self.html.index('</head>')
            self.html = self.html[:i] + '<style>\n' + FIG_CSS + '</style>\n' + self.html[i:]
        else:
            self.html = '<style>\n' + FIG_CSS + '</style>\n' + self.html

    def _one(self, old):
        c = self.html.count(old)
        assert c == 1, f'{os.path.basename(self.path)}: 기준 문자열이 {c}번 나옴: {old[:80]!r}'

    def insert_after(self, anchor, html):
        self._one(anchor)
        self.html = self.html.replace(anchor, anchor + html)

    def insert_before(self, anchor, html):
        self._one(anchor)
        self.html = self.html.replace(anchor, html + anchor)

    def replace(self, old, new):
        self._one(old)
        self.html = self.html.replace(old, new)

    def replace_re(self, pattern, new):
        ms = list(re.finditer(pattern, self.html, re.S))
        assert len(ms) == 1, f'{os.path.basename(self.path)}: 패턴이 {len(ms)}번: {pattern[:60]}'
        m = ms[0]
        self.html = self.html[:m.start()] + new + self.html[m.end():]

    def version(self):
        m = re.search(r'버전 (?:<b>)?(v?)(\d+)\.(\d+)(?:</b>)?', self.html)
        assert m, '문서 맨 위 버전 표기를 찾지 못함'
        return m

    def bump(self, history_text, date):
        """문서가 '버전 x.y'와 '변경 이력' 표를 쓰는 경우: 이전 판을 archive/<이름>_v<판>.html로 두고 판을 0.1 올린다."""
        m = self.version()
        pre, major, minor = m.group(1), int(m.group(2)), int(m.group(3))
        old_v, new_v = f'{major}.{minor}', f'{major}.{minor + 1}'
        base = os.path.splitext(os.path.basename(self.path))[0]
        arch_dir = os.path.join(os.path.dirname(self.path) or '.', 'archive')
        os.makedirs(arch_dir, exist_ok=True)
        arch = os.path.join(arch_dir, f'{base}_v{old_v}.html')
        if not os.path.exists(arch):
            shutil.copyfile(self.path, arch)
        whole = m.group(0)
        self.html = self.html.replace(whole, whole.replace(f'{pre}{old_v}', f'{pre}{new_v}'), 1)
        k = self.html.find('변경 이력')
        assert k >= 0, '변경 이력 절이 없음'
        rm = re.compile(r'<tr><td>(v?)\d+\.\d+</td>').search(self.html, k)
        assert rm, '변경 이력 표의 행을 찾지 못함'
        rel = os.path.relpath(arch, os.path.dirname(self.path) or '.').replace(os.sep, '/')
        row = (f'<tr><td>{rm.group(1)}{new_v}</td><td>{date}</td><td>{history_text} '
               f'<a href="{rel}">{rm.group(1)}{old_v} 보관본</a></td></tr>\n')
        self.html = self.html[:rm.start()] + row + self.html[rm.start():]
        return new_v

    def save(self):
        out = self.html.replace('\n', '\r\n') if self.crlf else self.html
        io.open(self.path, 'w', encoding='utf-8', newline='').write(out)


# ---------------------------------------------------------------- 점검·스크린샷
def check(path):
    s = io.open(path, encoding='utf-8').read()
    probs = []
    for m in re.finditer(r'<svg\b.*?</svg>', s, re.S):
        body = m.group(0)
        if re.search(r'<script|<foreignObject|<image|href="http', body):
            probs.append('svg 안에 script·foreignObject·image·외부 링크')
        if 'aria-label=' not in body[:400]:
            probs.append('svg에 aria-label 없음')
    figs = re.findall(r'<figure class="fig"[^>]*>.*?</figure>', s, re.S)
    for f in figs:
        if '<figcaption>' not in f:
            probs.append('figcaption 없는 그림')
    ids = re.findall(r'<figure class="fig" id="([^"]+)"', s)
    if len(ids) != len(set(ids)):
        probs.append('그림 id 중복')
    mids = re.findall(r'<marker id="([^"]+)"', s)
    if len(mids) != len(set(mids)):
        probs.append('marker id 중복 (Flow의 mid를 그림마다 다르게)')
    base = os.path.dirname(path) or '.'
    for h in re.findall(r'href="([^"#]+)', s):
        if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', h):   # https:, mailto: 등 외부 링크는 건너뜀
            continue
        if not os.path.exists(os.path.normpath(os.path.join(base, urllib.parse.unquote(h)))):
            probs.append(f'깨진 링크: {h}')
    anchors = set(re.findall(r'id="([^"]+)"', s))
    for a in re.findall(r'href="#([^"]+)"', s):
        if a not in anchors:
            probs.append(f'없는 앵커: #{a}')
    if re.search(r'<(script|link)[^>]+(src|href)="https?://', s):
        probs.append('외부 스크립트·스타일')
    tag = '[통과]' if not probs else '[문제]'
    print(f'{tag} {path} · 그림 {len(figs)}개')
    for p in probs:
        print('   -', p)
    return not probs


def _chrome():
    candidates = [
        shutil.which('chrome'),
        shutil.which('google-chrome'),
        shutil.which('chromium'),
        shutil.which('chromium-browser'),
        shutil.which('msedge'),
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
    ]
    for p in candidates:
        if p and os.path.exists(p):
            return p
    raise SystemExit('Chrome/Edge를 찾지 못했습니다')


def _headless_profile_dir():
    """Headless Chrome이 매 실행마다 빈 암호 확인(Windows LogonUserW -> Event 4625/4740)을 하지 않도록
    os_password_last_changed 캐시가 포함된 고정 프로필 폴더를 준비한다."""
    tmp = os.environ.get('TEMP') or os.environ.get('TMPDIR') or '/tmp'
    prof = os.path.join(tmp, 'docfig-chrome-profile')
    os.makedirs(prof, exist_ok=True)
    local_state = os.path.join(prof, 'Local State')
    src_state = os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\User Data\Local State')
    try:
        pw_mgr = {'os_password_blank': False, 'os_password_last_changed': '13359901926290193'}
        if os.path.exists(src_state):
            with io.open(src_state, encoding='utf-8') as f:
                pw_mgr = json.load(f).get('password_manager', pw_mgr)
        state = {}
        if os.path.exists(local_state):
            with io.open(local_state, encoding='utf-8') as f:
                state = json.load(f)
        cur_pm = state.get('password_manager') if isinstance(state.get('password_manager'), dict) else {}
        if cur_pm.get('os_password_last_changed') != pw_mgr.get('os_password_last_changed'):
            cur_pm.update(pw_mgr)
            state['password_manager'] = cur_pm
            with io.open(local_state, 'w', encoding='utf-8') as f:
                json.dump(state, f)
    except Exception:
        pass
    return prof


def shot(path, out_dir):
    """그림마다 밝은·어두운 화면 PNG. 문서의 <style>을 함께 넣어 실제 모양 그대로 찍는다."""
    s = io.open(path, encoding='utf-8').read()
    style = ''.join(re.findall(r'<style>.*?</style>', s, re.S))
    figs = re.findall(r'<figure class="fig"[^>]*>.*?</figure>', s, re.S)
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(path))[0]
    chrome = _chrome()
    profile_dir = _headless_profile_dir()
    outs = []
    for i, f in enumerate(figs, 1):
        # 그림 자체의 viewBox(시작점이 0 0이 아닐 수 있음). 화살촉 marker의 viewBox를 읽지 않게 <svg 태그에서만 찾는다
        vb = re.search(r'<svg viewBox="[-\d.]+ [-\d.]+ ([\d.]+) ([\d.]+)"', f)
        h = int(float(vb.group(2))) + 260 if vb else 900
        for theme in ('light', 'dark'):
            attr = ' data-theme="dark"' if theme == 'dark' else ' data-theme="light"'
            page = (f'<!doctype html><html{attr}><head><meta charset="utf-8">{style}</head>'
                    f'<body style="margin:0;padding:16px;width:1060px"><main>{f}</main></body></html>')
            hp = os.path.join(out_dir, f'{base}_{i}_{theme}.html')
            io.open(hp, 'w', encoding='utf-8').write(page)
            png = os.path.abspath(os.path.join(out_dir, f'{base}_{i}_{theme}.png'))
            uri = pathlib.Path(hp).resolve().as_uri()
            subprocess.run([chrome, '--headless=new', '--disable-gpu', '--hide-scrollbars',
                            '--no-first-run', '--no-default-browser-check', '--password-store=basic',
                            f'--user-data-dir={profile_dir}',
                            f'--window-size=1100,{h}', f'--screenshot={png}', uri],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
            outs.append(png)
    for o in outs:
        print(o)
    return outs


if __name__ == '__main__':
    if len(sys.argv) >= 3 and sys.argv[1] == 'check':
        ok = all([check(p) for p in sys.argv[2:]])
        sys.exit(0 if ok else 1)
    if len(sys.argv) >= 3 and sys.argv[1] == 'shot':
        default_tmp = os.path.join(os.environ.get('TEMP') or os.environ.get('TMPDIR') or '/tmp', 'docfig')
        shot(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else default_tmp)
        sys.exit(0)
    print(__doc__)
