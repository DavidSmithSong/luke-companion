#!/usr/bin/env python3
"""
为路加福音每章生成 NotebookLM 输入文档。
用法：python3 generate_chapter.py <章节号>
例如：python3 generate_chapter.py 1
输出：chapters/luke-1.md
"""

import sys
import os
import re
import httpx
from google import genai
from pathlib import Path

# 从 .env 文件加载 key（优先于环境变量）
def _load_env():
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

_load_env()

_gemini_client = None

def _check_api_key():
    global _gemini_client
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        print("❌ 未找到 GEMINI_API_KEY。")
        print()
        print("请在本目录创建 .env 文件：")
        print("  echo 'GEMINI_API_KEY=你的key' > .env")
        sys.exit(1)
    _gemini_client = genai.Client(api_key=key)

# ── 圣经文本抓取 ──────────────────────────────────────────────

def fetch_scripture(chapter: int) -> str:
    """从 cnbible.com 抓取路加福音某章的和合本经文。"""
    url = f"https://cnbible.com/luke/{chapter}.htm"
    try:
        r = httpx.get(url, timeout=15, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
    except Exception as e:
        print(f"  ⚠️  网络抓取失败（{e}），使用占位文本")
        return f"【路加福音第{chapter}章经文】\n（请手动粘贴经文）"

    # cnbible.com 的简体和合本在 class="btext2" 的 span 里
    # 每节格式：<span class="reftext">节号链接</span><span class="btext2">经文</span>
    text = r.text

    # 提取节号和简体经文
    # 节号在 href="/luke/章-节.htm" 里，经文在 btext2 span 里
    pattern = rf'href="/luke/{chapter}-(\d+)\.htm"[^>]*><b>\1</b></a></span><span class="btext2">(.*?)</span>'
    matches = re.findall(pattern, text, re.DOTALL)

    if not matches:
        # 备用：只提取 btext2 的内容（顺序提取）
        verses = re.findall(r'<span class="btext2">(.*?)</span>', text)
        if not verses:
            return f"【路加福音第{chapter}章经文】\n（请手动粘贴经文）"
        lines = []
        for i, v in enumerate(verses, 1):
            clean = re.sub(r'<[^>]+>', '', v).strip()
            if clean:
                lines.append(f"[{chapter}:{i}] {clean}")
        return "\n".join(lines)

    lines = []
    for verse_num, content in matches:
        clean = re.sub(r'<[^>]+>', '', content).strip()
        clean = re.sub(r'\s+', ' ', clean)
        if clean:
            lines.append(f"[{chapter}:{verse_num}] {clean}")

    return "\n".join(lines)


# ── Gemini 生成辅助内容 ───────────────────────────────────────

SYSTEM_PROMPT = """你是一位帮助普通信徒读圣经的助手。
你的读者是中国大陆的退休老人，受教育程度中等，对圣经不熟悉但愿意学习。
写作要求：
- 语言口语化、亲切，像对父母说话
- 不使用神学术语（不说"救赎论""护理""末世论"等）
- 把神学真理融入具体场景和生活类比
- 简体中文，不超过指定字数"""


def generate_study_content(chapter: int, scripture: str) -> dict:
    """调用 Gemini 生成背景、类比和问题。"""
    full_prompt = f"""{SYSTEM_PROMPT}

以下是路加福音第{chapter}章的经文：

{scripture}

请为这章经文生成以下内容，帮助普通老人读懂这章：

1. **历史文化背景**（150字以内）
   解释这章涉及的时代、地点、人物背景。用"那个时候"开头，像讲故事一样。

2. **平行参考**（100字以内）
   找出马太福音或马可福音中与本章同一事件的平行段落，简单说明异同。
   如果本章内容在其他福音书中没有平行段落，就写"本章内容为路加独有"并简要说明价值。

3. **现代类比**（2个，每个50字以内）
   把本章的核心场景或人物，类比为今天中国日常生活中的情境。
   例如："税吏撒该爬上树——就像一个被同事孤立的人，站在会议室门口偷偷往里看"

4. **思考问题**（3个）
   - 问题要具体、有温度，引发真实生活的联想
   - 不要出现"属灵""蒙恩""神的旨意"等宗教术语
   - 可以是开放式，也可以是"你们有没有……"的邀请式
   - 每个问题不超过60字

请按如下格式输出（不要加多余说明）：

## 背景
[内容]

## 平行参考
[内容]

## 现代类比
类比1：[内容]
类比2：[内容]

## 思考问题
问题1：[内容]
问题2：[内容]
问题3：[内容]"""

    response = _gemini_client.models.generate_content(
        model="models/gemini-flash-latest",
        contents=full_prompt,
    )
    raw = response.text

    # 解析各个部分
    sections = {}
    current_key = None
    current_lines = []

    for line in raw.split("\n"):
        if line.startswith("## "):
            if current_key:
                sections[current_key] = "\n".join(current_lines).strip()
            current_key = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_key:
        sections[current_key] = "\n".join(current_lines).strip()

    return sections


# ── 组装 Markdown 文档 ────────────────────────────────────────

def build_markdown(chapter: int, scripture: str, sections: dict) -> str:
    background = sections.get("背景", "（待填写）")
    parallel = sections.get("平行参考", "（待填写）")
    analogies_raw = sections.get("现代类比", "")
    questions_raw = sections.get("思考问题", "")

    # 提取类比列表
    analogy_lines = [l for l in analogies_raw.split("\n") if l.strip().startswith("类比")]
    analogies = "\n".join(f"- {l.split('：', 1)[-1].strip()}" for l in analogy_lines)

    # 提取问题列表
    question_lines = [l for l in questions_raw.split("\n") if l.strip().startswith("问题")]
    questions = "\n".join(f"- {l.split('：', 1)[-1].strip()}" for l in question_lines)

    return f"""# 路加福音第{chapter}章 · NotebookLM 输入文档

> 本文档供上传至 NotebookLM 生成约10分钟中文播客讲解。
> 建议生成时在「Customize」中注明：面向中国大陆60岁以上的普通读经老人，语言亲切口语化。

---

## 一、本章经文（和合本）

{scripture}

---

## 二、历史文化背景

{background}

---

## 三、平行参考

{parallel}

---

## 四、现代生活类比

以下类比帮助理解本章核心场景，可在播客中自然融入：

{analogies if analogies else analogies_raw}

---

## 五、引导思考的问题

请在播客对话中自然带出以下问题，引导听众联系自己的生活：

{questions if questions else questions_raw}

---

*以上内容由 Claude 辅助生成，供参考使用。*
"""


# ── 生成章节页面（Astro 文件）────────────────────────────────

def build_astro_page(chapter: int, title: str, scripture: str, sections: dict) -> str:
    background = sections.get("背景", "").replace('"', '\\"')
    parallel = sections.get("平行参考", "").replace('"', '\\"')
    questions_raw = sections.get("思考问题", "")
    analogies_raw = sections.get("现代类比", "")

    # 把问题解析成列表
    question_lines = [l.split("：", 1)[-1].strip()
                      for l in questions_raw.split("\n")
                      if l.strip().startswith("问题")]

    # 补足3个问题
    while len(question_lines) < 3:
        question_lines.append("（待补充）")

    q_array = ",\n  ".join(
        f'{{ q: `{q}` }}' for q in question_lines[:3]
    )

    # 提取类比
    analogy_lines = [l.split("：", 1)[-1].strip()
                     for l in analogies_raw.split("\n")
                     if l.strip().startswith("类比")]
    analogies_html = "".join(f"<li>{a}</li>" for a in analogy_lines)

    # 上一章/下一章
    prev_link = f'<a href="/luke/{chapter-1}" class="nav-btn">← 第 {chapter-1} 章</a>' if chapter > 1 else ""
    next_link = f'<a href="/luke/{chapter+1}" class="nav-btn">第 {chapter+1} 章 →</a>' if chapter < 24 else ""

    # 经文处理（转义反引号）
    scripture_escaped = scripture.replace("`", "\\`")
    background_escaped = sections.get("背景", "").replace("`", "\\`").replace("**", "").replace("*", "")
    parallel_escaped = sections.get("平行参考", "").replace("`", "\\`").replace("**", "").replace("*", "")

    return f"""---
import BaseLayout from '../../layouts/BaseLayout.astro';

const chapter = {chapter};
const title = "{title}";
const videoSrc = ""; // NotebookLM 视频下载后放到 public/video/，如 "/video/luke-{chapter}.mp4"

const scripture = `{scripture_escaped}`;
const background = `{background_escaped}`;
const parallel = `{parallel_escaped}`;
const questions = [
  {q_array}
];
---
<BaseLayout title={{`第 ${{chapter}} 章：${{title}} · 路加福音陪读`}}>
  <style>
    .toc {{ position:fixed;top:50%;left:max(1rem,calc(50% - 360px - 148px));transform:translateY(-50%);display:flex;flex-direction:column;gap:.35rem;width:120px;z-index:100; }}
    .toc a {{ display:block;padding:.45rem .7rem;font-size:.8rem;color:var(--color-text-muted);text-decoration:none;border-left:2px solid var(--color-border);border-radius:0 6px 6px 0;line-height:1.4;transition:color .15s,border-color .15s,background .15s; }}
    .toc a:hover,.toc a.active {{ color:var(--color-accent-dark);border-color:var(--color-accent);background:var(--color-accent-light);font-weight:600; }}
    @media (max-width:1000px) {{ .toc {{ display:none; }} }}
    .nav-back {{ display:inline-flex;align-items:center;gap:.4rem;color:var(--color-accent-dark);text-decoration:none;font-size:.85rem;margin-bottom:1.5rem; }}
    .nav-back:hover {{ text-decoration:underline; }}
    .chapter-label {{ font-size:.85rem;color:var(--color-text-muted);margin-bottom:.3rem; }}
    .chapter-title {{ font-family:var(--font-serif);font-size:1.5rem;line-height:1.4;margin-bottom:2rem; }}
    .video-section {{ background:var(--color-surface);border:1px solid var(--color-border);border-radius:12px;padding:1.2rem 1.3rem;margin-bottom:2rem; }}
    .video-section h2 {{ font-family:var(--font-serif);font-size:1rem;margin-bottom:.8rem;color:var(--color-accent-dark); }}
    .video-placeholder {{ background:var(--color-accent-light);border-radius:8px;padding:1.2rem;text-align:center;color:var(--color-text-muted);font-size:.9rem;line-height:2; }}
    video {{ width:100%;border-radius:8px;max-height:400px;background:#000; }}
    .tts-bar {{ display:flex;align-items:center;gap:.6rem;margin-top:.8rem; }}
    .tts-btn {{ display:inline-flex;align-items:center;gap:.35rem;padding:.4rem .9rem;background:var(--color-accent-light);color:var(--color-accent-dark);border:1px solid var(--color-border);border-radius:99px;font-size:.82rem;cursor:pointer;font-family:var(--font-sans); }}
    .tts-btn:hover,.tts-btn.playing {{ background:var(--color-accent);color:white;border-color:var(--color-accent); }}
    .tts-hint {{ font-size:.78rem;color:var(--color-text-muted); }}
    .content-block {{ margin-bottom:2rem; }}
    .content-block h2 {{ font-family:var(--font-serif);font-size:1rem;color:var(--color-text-muted);margin-bottom:.8rem;padding-bottom:.4rem;border-bottom:1px solid var(--color-border); }}
    .scripture-text {{ font-family:var(--font-serif);font-size:.95rem;line-height:2.2;white-space:pre-wrap;color:var(--color-text); }}
    .prose {{ font-size:.9rem;line-height:1.9; }}
    .questions-list {{ display:grid;gap:1.2rem; }}
    .question-card {{ background:var(--color-surface);border:1px solid var(--color-border);border-left:3px solid var(--color-accent);border-radius:0 8px 8px 0;padding:.9rem 1rem; }}
    .question-num {{ font-size:.75rem;color:var(--color-accent);font-weight:700;margin-bottom:.3rem; }}
    .question-text {{ font-family:var(--font-serif);font-size:.95rem;line-height:1.8;margin-bottom:.75rem; }}
    .answer-label {{ font-size:.78rem;color:var(--color-text-muted);margin-bottom:.3rem; }}
    .answer-box {{ width:100%;box-sizing:border-box;min-height:80px;padding:.6rem .75rem;font-family:var(--font-sans);font-size:.88rem;line-height:1.7;color:var(--color-text);background:var(--color-bg);border:1px solid var(--color-border);border-radius:6px;resize:vertical;outline:none;transition:border-color .15s; }}
    .answer-box:focus {{ border-color:var(--color-accent); }}
    .save-hint {{ font-size:.75rem;color:var(--color-text-muted);margin-top:.3rem;min-height:1.2em;transition:opacity .3s; }}
    .save-hint.saved {{ color:#6a9e6a; }}
    .chapter-nav {{ display:flex;justify-content:space-between;margin-top:3rem;padding-top:1.5rem;border-top:1px solid var(--color-border); }}
    .nav-btn {{ display:inline-flex;align-items:center;gap:.4rem;padding:.6rem 1.2rem;background:var(--color-accent-light);color:var(--color-accent-dark);border-radius:8px;text-decoration:none;font-size:.9rem;transition:background .15s; }}
    .nav-btn:hover {{ background:var(--color-accent);color:white; }}
  </style>

  <nav class="toc" aria-label="页面目录">
    <a href="#video">🎬 视频</a>
    <a href="#scripture">📖 经文</a>
    <a href="#background">🌍 背景</a>
    <a href="#parallel">📚 参考</a>
    <a href="#questions">💭 思考</a>
  </nav>

  <a href="/" class="nav-back">← 返回章节目录</a>
  <div class="chapter-label">路加福音 · 第 {{chapter}} 章</div>
  <h1 class="chapter-title">{{title}}</h1>

  <div id="video" class="video-section">
    <h2>🎬 本章视频讲解（约10分钟）</h2>
    {{videoSrc ? (
      <><video controls src={{videoSrc}} preload="metadata"></video><p style="font-size:.85rem;color:var(--color-text-muted);margin-top:.6rem">建议先看视频，再读经文和思考问题</p></>
    ) : (
      <div class="video-placeholder">视频整理中，即将上线……<br/><small>可先阅读下方经文和背景资料</small></div>
    )}}
  </div>

  <div id="scripture" class="content-block">
    <h2>📖 本章经文（和合本）</h2>
    <p class="scripture-text" id="scripture-text">{{scripture}}</p>
    <div class="tts-bar">
      <button class="tts-btn" id="tts-btn" onclick="toggleRead()">🔊 朗读经文</button>
      <span class="tts-hint">点击朗读，再次点击停止</span>
    </div>
  </div>

  <div id="background" class="content-block">
    <h2>🌍 背景资料</h2>
    <p class="prose">{{background}}</p>
  </div>

  <div id="parallel" class="content-block">
    <h2>📚 平行参考</h2>
    <p class="prose">{{parallel}}</p>
  </div>

  <div id="questions" class="content-block">
    <h2>💭 思考与交流</h2>
    <div class="questions-list">
      {{questions.map((item, i) => (
        <div class="question-card">
          <div class="question-num">问题 {{i + 1}}</div>
          <div class="question-text">{{item.q}}</div>
          <div class="answer-label">您的想法：</div>
          <textarea class="answer-box" data-key={{`luke-{chapter}-q-${{i}}`}} placeholder="在这里写下您的想法……" oninput="saveAnswer(this)"></textarea>
          <div class="save-hint" id={{`hint-${{i}}`}}></div>
        </div>
      ))}}
    </div>
  </div>

  <div class="chapter-nav">
    {prev_link}
    {next_link}
  </div>

  <script>
    let utterance = null;
    function toggleRead() {{
      const btn = document.getElementById('tts-btn');
      const text = document.getElementById('scripture-text')?.textContent || '';
      if (window.speechSynthesis.speaking) {{
        window.speechSynthesis.cancel();
        btn.textContent = '🔊 朗读经文';
        btn.classList.remove('playing');
        return;
      }}
      utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = 'zh-CN';
      utterance.rate = 0.85;
      utterance.onend = () => {{ btn.textContent = '🔊 朗读经文'; btn.classList.remove('playing'); }};
      window.speechSynthesis.speak(utterance);
      btn.textContent = '⏹ 停止朗读';
      btn.classList.add('playing');
    }}
    window.toggleRead = toggleRead;

    document.querySelectorAll('.answer-box').forEach((el) => {{
      const saved = localStorage.getItem(el.dataset.key);
      if (saved) {{ el.value = saved; el.style.height = el.scrollHeight + 'px'; }}
    }});

    let saveTimers = {{}};
    function saveAnswer(el) {{
      el.style.height = 'auto';
      el.style.height = el.scrollHeight + 'px';
      const key = el.dataset.key;
      clearTimeout(saveTimers[key]);
      saveTimers[key] = setTimeout(() => {{
        localStorage.setItem(key, el.value);
        const idx = key.split('-').pop();
        const hint = document.getElementById('hint-' + idx);
        if (hint) {{ hint.textContent = '✓ 已保存'; hint.classList.add('saved'); setTimeout(() => {{ hint.textContent = ''; hint.classList.remove('saved'); }}, 2000); }}
      }}, 600);
    }}
    window.saveAnswer = saveAnswer;

    const sections = ['video','scripture','background','parallel','questions'];
    const tocLinks = {{}};
    sections.forEach(id => {{ const a = document.querySelector(`.toc a[href="#${{id}}"]`); if (a) tocLinks[id] = a; }});
    const obs = new IntersectionObserver((entries) => {{
      entries.forEach(e => {{ if (e.isIntersecting) {{ Object.values(tocLinks).forEach(a => a.classList.remove('active')); if (tocLinks[e.target.id]) tocLinks[e.target.id].classList.add('active'); }} }});
    }}, {{ rootMargin: '-20% 0px -60% 0px' }});
    sections.forEach(id => {{ const el = document.getElementById(id); if (el) obs.observe(el); }});
  </script>
</BaseLayout>
"""


# ── 章节标题映射 ─────────────────────────────────────────────

CHAPTER_TITLES = {
    1: "天使报信与施洗约翰的诞生",
    2: "耶稣的降生",
    3: "施洗约翰与耶稣受洗",
    4: "旷野受试探与拿撒勒讲道",
    5: "呼召门徒与洁净麻风病人",
    6: "登山宝训",
    7: "百夫长的仆人与寡妇的儿子",
    8: "撒种的比喻与平静风浪",
    9: "五饼二鱼与变容",
    10: "差遣七十二人与好撒玛利亚人",
    11: "主祷文与光明的比喻",
    12: "不要忧虑与儆醒的比喻",
    13: "无花果树与窄门",
    14: "宴席的比喻",
    15: "迷失的羊、失落的钱币与浪子",
    16: "不义管家与富人与拉撒路",
    17: "饶恕与感恩的十个麻风病人",
    18: "法官与寡妇、法利赛人与税吏",
    19: "撒该与进入耶路撒冷",
    20: "葡萄园的比喻与纳税问题",
    21: "寡妇的两个小钱与末世预言",
    22: "最后的晚餐与被捕",
    23: "受审与十字架",
    24: "复活与升天",
}


# ── 主程序 ────────────────────────────────────────────────────

def main():
    _check_api_key()

    if len(sys.argv) < 2:
        print("用法：python3 generate_chapter.py <章节号>")
        print("例如：python3 generate_chapter.py 1")
        sys.exit(1)

    chapter = int(sys.argv[1])
    if not 1 <= chapter <= 24:
        print("章节号必须在 1-24 之间")
        sys.exit(1)

    title = CHAPTER_TITLES.get(chapter, f"第{chapter}章")
    print(f"\n📖 路加福音第{chapter}章：{title}")

    # 1. 抓取经文
    print("  → 抓取经文...")
    scripture = fetch_scripture(chapter)
    print(f"     {len(scripture)} 字符")

    # 2. 生成辅助内容
    print("  → 调用 Gemini 生成背景/类比/问题...")
    sections = generate_study_content(chapter, scripture)
    print("     完成")

    # 3. 输出 NotebookLM 输入文档
    Path("chapters").mkdir(exist_ok=True)
    md_path = f"chapters/luke-{chapter}.md"
    md_content = build_markdown(chapter, scripture, sections)
    Path(md_path).write_text(md_content, encoding="utf-8")
    print(f"  ✅ NotebookLM 输入文档：{md_path}")

    # 4. 输出网站 Astro 页面
    astro_dir = Path("site/src/pages/luke")
    astro_dir.mkdir(parents=True, exist_ok=True)
    astro_path = astro_dir / f"{chapter}.astro"
    astro_content = build_astro_page(chapter, title, scripture, sections)
    astro_path.write_text(astro_content, encoding="utf-8")
    print(f"  ✅ 网站页面：{astro_path}")

    print(f"\n下一步：")
    print(f"  1. 打开 {md_path}，上传到 notebooklm.google.com 生成 Video Overview")
    print(f"  2. 下载视频，保存为 site/public/video/luke-{chapter}.mp4")
    print(f"  3. 在 {astro_path} 中将 videoSrc 改为 \"/video/luke-{chapter}.mp4\"")
    print(f"  4. 更新 site/src/pages/index.astro 中的 publishedChapters 数组，加入 {chapter}")


if __name__ == "__main__":
    main()
