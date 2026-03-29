# Knowledge Crawler

用于补充力量举动作技术知识库的轻量爬虫项目。

目标：
- 抓取公开网页中的动作技术内容
- 清洗成结构化 Markdown / JSON
- 为后续 LLM 知识库整理提供稳定原料

## 目录

- `crawler/`
  - `cli.py`：命令行入口
  - `config.py`：数据模型与配置读取
  - `fetch.py`：抓取与 robots 检查
  - `parse.py`：正文抽取与结构化清洗
  - `pipeline.py`：抓取主流程
  - `store.py`：落盘与索引
- `seeds/`
  - `sources.example.yaml`：示例来源配置

## 安装

```bash
cd /Users/liumiao/Documents/trae_projects/model/knowledge_crawler
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 运行

先复制示例配置：

```bash
cd /Users/liumiao/Documents/trae_projects/model/knowledge_crawler
cp seeds/sources.example.yaml seeds/sources.yaml
```

抓取：

```bash
cd /Users/liumiao/Documents/trae_projects/model/knowledge_crawler
python -m crawler.cli crawl --config seeds/sources.yaml
```

输出默认会写到：

- `output/raw/`
- `output/markdown/`
- `output/index.jsonl`

## 现阶段限制

- 当前版本更适合抓“单篇文章页”或“单个视频说明页”
- 对于 bilibili 这种作者频道页，当前版本会先把它当单页来源保存下来
- 如果要把频道页自动展开成“多个视频页”，需要下一步补：
  - 列表页发现
  - 分页抓取
  - 视频详情页抽取

## 说明

- 当前版本默认只做单页抓取和清洗骨架
- 不内置大规模站点递归爬取，避免一开始就把复杂度拉满
- 后续可以按来源逐步补：
  - 列表页发现
  - 分页抓取
  - 视频站点描述抓取
  - 去重与质量打分
