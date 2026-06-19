# 父母读经 项目上下文

## 项目定位

- **目标**：为宋化富的父母提供路加福音陪读网站
- **读者**：爸爸（初中学历）、妈妈（小学三年级），56 岁，持续阅读中
- **气质**：亲切口语化，无神学术语，有生活类比；不是讲道，是陪伴阅读

## 技术栈

- **内容生成**：`generate_chapter.py`（爬取和合本经文 → Gemini AI 生成辅助内容 → 输出 MD）
- **视频**：上传 `chapters/luke-N.md` 到 Google NotebookLM 生成播客视频，下载到 `site/public/video/luke-N.mp4`
- **网站**：Astro 静态站点（`site/`），褐色温暖主题，Noto Serif SC
- **部署**：Vercel（`vercel.json` 已配置）

## 工作流程

```
python3 generate_chapter.py N
  → chapters/luke-N.md（上传 NotebookLM）
  → site/src/pages/luke/N.astro（自动生成网页）
手动：下载视频 → 更新 index.astro publishedChapters 数组
```

## 当前进度

- 已完成：第 1 章与第 2 章（网页已生成，并完成了第 2 章基于高信息密度/故事叙述风格的内容优化与视频绑定）
- 进行中：第 3 章内容准备

## 下一步优化方向

- 保持基于高信息密度、叙事感强（gemini-2.5-flash 新提示词）的策略生成后续第 3-24 章的 MD 和 Astro 页面。
- 逐步推进到路加福音 24 章。

## 铁律

- 目标用户是教育水平不高的老人，语言必须简单、具体、有生活感
- 不改动已发布章节（`publishedChapters` 中已有的）的 Astro 页面样式
- 视频文件命名：`luke-N.mp4`，存入 `site/public/video/`
