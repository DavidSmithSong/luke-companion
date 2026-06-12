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
import anthropic
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

def _check_api_key():
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key.startswith("sk-ant-"):
        print("❌ 未找到有效的 Anthropic API key。")
        print()
        print("请按以下步骤设置：")
        print("  1. 访问 https://console.anthropic.com/settings/keys")
        print("  2. 创建新 key（以 sk-ant- 开头）")
        print("  3. 在本目录创建 .env 文件：")
        print("     echo 'ANTHROPIC_API_KEY=sk-ant-你的key' > .env")
        sys.exit(1)

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


# ── Claude 生成辅助内容 ───────────────────────────────────────

SYSTEM_PROMPT = """你是一位帮助普通信徒读圣经的助手。
你的读者是中国大陆的退休老人，受教育程度中等，对圣经不熟悉但愿意学习。
写作要求：
- 语言口语化、亲切，像对父母说话
- 不使用神学术语（不说"救赎论""护理""末世论"等）
- 把神学真理融入具体场景和生活类比
- 简体中文，不超过指定字数"""


def generate_study_content(chapter: int, scripture: str) -> dict:
    """调用 Claude 生成背景、类比和问题。"""
    client = anthropic.Anthropic()

    prompt = f"""以下是路加福音第{chapter}章的经文：

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

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[
            {"role": "user", "content": prompt}
        ],
        system=SYSTEM_PROMPT
    )

    raw = message.content[0].text

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
const audioSrc = ""; // 上传音频后填入路径，如 "/audio/luke-{chapter}.mp3"

const scripture = `{scripture_escaped}`;
const background = `{background_escaped}`;
const parallel = `{parallel_escaped}`;
const questions = [
  {q_array}
];
---
<BaseLayout title={{`第 ${{chapter}} 章：${{title}} · 路加福音陪读`}}>
  <style>
    .nav-back {{ display:inline-flex;align-items:center;gap:.4rem;color:var(--color-accent-dark);text-decoration:none;font-size:.85rem;margin-bottom:1.5rem; }}
    .nav-back:hover {{ text-decoration:underline; }}
    .chapter-label {{ font-size:.85rem;color:var(--color-text-muted);margin-bottom:.3rem; }}
    .chapter-title {{ font-family:var(--font-serif);font-size:1.5rem;line-height:1.4;margin-bottom:2rem; }}
    .audio-section {{ background:var(--color-surface);border:1px solid var(--color-border);border-radius:12px;padding:1.2rem 1.3rem;margin-bottom:2rem; }}
    .audio-section h2 {{ font-family:var(--font-serif);font-size:1rem;margin-bottom:.8rem;color:var(--color-accent-dark); }}
    .audio-placeholder {{ background:var(--color-accent-light);border-radius:8px;padding:1.2rem;text-align:center;color:var(--color-text-muted);font-size:.9rem; }}
    audio {{ width:100%;border-radius:8px; }}
    .content-block {{ margin-bottom:2rem; }}
    .content-block h2 {{ font-family:var(--font-serif);font-size:1rem;color:var(--color-text-muted);margin-bottom:.8rem;padding-bottom:.4rem;border-bottom:1px solid var(--color-border); }}
    .scripture-text {{ font-family:var(--font-serif);font-size:.95rem;line-height:2.1;white-space:pre-wrap; }}
    details summary {{ cursor:pointer;color:var(--color-accent-dark);font-size:.9rem;padding:.5rem 0;user-select:none; }}
    details[open] summary {{ margin-bottom:.8rem; }}
    .prose {{ font-size:.9rem;line-height:1.9; }}
    .questions-list {{ display:grid;gap:.8rem; }}
    .question-card {{ background:var(--color-surface);border:1px solid var(--color-border);border-left:3px solid var(--color-accent);border-radius:0 8px 8px 0;padding:.9rem 1rem; }}
    .question-num {{ font-size:.75rem;color:var(--color-accent);font-weight:700;margin-bottom:.3rem; }}
    .question-text {{ font-family:var(--font-serif);font-size:.95rem;line-height:1.8; }}
    .chapter-nav {{ display:flex;justify-content:space-between;margin-top:3rem;padding-top:1.5rem;border-top:1px solid var(--color-border); }}
    .nav-btn {{ display:inline-flex;align-items:center;gap:.4rem;padding:.6rem 1.2rem;background:var(--color-accent-light);color:var(--color-accent-dark);border-radius:8px;text-decoration:none;font-size:.9rem;transition:background .15s; }}
    .nav-btn:hover {{ background:var(--color-accent);color:white; }}
  </style>

  <a href="/" class="nav-back">← 返回章节目录</a>
  <div class="chapter-label">路加福音 · 第 {{chapter}} 章</div>
  <h1 class="chapter-title">{{title}}</h1>

  <div class="audio-section">
    <h2>🎧 本章音频讲解（约10分钟）</h2>
    {{audioSrc ? (
      <><audio controls src={{audioSrc}}></audio><p style="font-size:.85rem;color:var(--color-text-muted);margin-top:.6rem">建议先听音频，再读经文和思考问题</p></>
    ) : (
      <div class="audio-placeholder">音频整理中，即将上线……<br/><small>可先阅读下方经文和背景资料</small></div>
    )}}
  </div>

  <div class="content-block">
    <h2>📖 本章经文（和合本）</h2>
    <details><summary>点击展开经文</summary><p class="scripture-text">{{scripture}}</p></details>
  </div>

  <div class="content-block">
    <h2>🌍 背景资料</h2>
    <p class="prose">{{background}}</p>
  </div>

  <div class="content-block">
    <h2>📚 平行参考</h2>
    <p class="prose">{{parallel}}</p>
  </div>

  <div class="content-block">
    <h2>💭 思考与交流</h2>
    <div class="questions-list">
      {{questions.map((item, i) => (
        <div class="question-card">
          <div class="question-num">问题 {{i + 1}}</div>
          <div class="question-text">{{item.q}}</div>
        </div>
      ))}}
    </div>
  </div>

  <div class="chapter-nav">
    {prev_link}
    {next_link}
  </div>
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
    print("  → 调用 Claude 生成背景/类比/问题...")
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
    print(f"  1. 打开 {md_path}，上传到 notebooklm.google.com 生成音频")
    print(f"  2. 下载音频，保存为 site/public/audio/luke-{chapter}.mp3")
    print(f"  3. 在 {astro_path} 中将 audioSrc 改为 \"/audio/luke-{chapter}.mp3\"")
    print(f"  4. 更新 site/src/pages/index.astro 中的 publishedChapters 数组，加入 {chapter}")


if __name__ == "__main__":
    main()
