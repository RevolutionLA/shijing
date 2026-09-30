# data/

| 文件 | 作用 | 来源与许可 |
|---|---|---|
| `raw/shijing.txt` | 原始抓取文本，**不作修改地存档** | 仓库作者早年自网页抓取 |
| `corpus.json` | 结构化语料：305 篇 / 30 组，含 `findings` 修复记录 | 由 `shijing build` 从 `raw/` 确定性生成 |
| `books/<slug>/raw.json` | 四书经文的上游文件，同样**原样存档**（`lunyu`/`mengzi`/`daxue`/`zhongyong`） | chinese-poetry，**MIT**，见下 |
| `books/<slug>/corpus.json` | 四书的结构化语料 | 由 `shijing --book 论语 build` 确定性生成 |
| `books/LICENSE.chinese-poetry.txt` | 上游 MIT 许可证全文 | MIT 要求随副本保留，不得删 |
| `overrides.json` | 自动归组平票时的人工裁定表，逐条附理由 | 本项目，判断依据写在每条 `reason` 里 |
| `t2s.tsv` | 繁→简归一表（4053 条非恒等映射），统计用简体、展示留原文 | 构建期由 `zhconv` 生成后冻结，运行期零依赖 |
| `rhyme_baxter1992.csv` | 逐句韵脚标注：是否入韵、韵脚字及其位置、章内局部韵标 | 见下 |

## 四书的出处

- 上游：**[chinese-poetry](https://github.com/chinese-poetry/chinese-poetry)**
  （JackeyGao 等），仓库许可为 **The MIT License**，全文已随副本存于
  `books/LICENSE.chinese-poetry.txt`。
- 只取**经文**，不取注疏、集注、译文。取用文件与并入时的上游 commit
  （`b8594f81a89752241442f2ce267d6f66f96704ee`）及 blob 校验：

  | 本地存档 | 上游路径 | blob SHA-1 | 字节 |
  |---|---|---|---|
  | `books/lunyu/raw.json` | `论语/lunyu.json` | `5b45b298f4e42917b94a2687399fa8307b044ffc` | 74,799 |
  | `books/mengzi/raw.json` | `四书五经/mengzi.json` | `8a19e260abadf2c8a0ce274c22c9a2b59c136749` | 146,745 |
  | `books/daxue/raw.json` | `四书五经/daxue.json` | `14cbc1ef8fbab503703b3f6d6edf019abb8b1ff0` | 6,767 |
  | `books/zhongyong/raw.json` | `四书五经/zhongyong.json` | `9ef84a1c656f313308cefcbc14dea15d694996e4` | 13,889 |

  这四条哈希就是 git 的对象校验和，`tests/test_books.py::test_四书原文存档与上游逐字节一致`
  会重算并比对——所以"原样存档"不是说法，是被钉住的。
- 实测规模：《论语》20 篇 512 段 15,917 字、《孟子》14 篇 690 段 35,388 字、
  《大学》1 篇 16 段 1,753 字、《中庸》1 篇 39 段 3,566 字（简体字计数，与
  `tests/test_books.py::SIZING` 同一套常数，改动会被测试拦住）。
- 已知的两处不完美，都不是本项目引入的：《孟子》的 690 段与通行本的 261 章不是一回事；
  《论语》是简体而其余三书是繁体。详见根目录 README 的"诚实的边界"。

## `rhyme_baxter1992.csv` 的出处

原始出处：**Baxter, W. H. (1992). *A Handbook of Old Chinese Phonology*。**
该书的《诗经》押韵字表被整理为 CLDF 数据集
[`hanproj/baxterocrhymes`](https://github.com/hanproj/baxterocrhymes)（其
`metadata.json` 标注许可为 **CC-BY-4.0**）。本仓库取其 `cldf/examples.csv`
裁剪为如下 8 列，并做了两处转换：

- `clause` 一列去掉原书的韵脚字母标记（a/b/x）与标点，只留汉字，并按
  `t2s.tsv` 归一，以便与 `corpus.json` 逐字比对；
- 行序按篇内出现次序重排，`idx` 为篇内全局序号。

| 列 | 含义 |
|---|---|
| `poem` | 篇序号，1–305，与**诗经** `corpus.json` 的 `idx` 同一套（《毛诗》序）。四书并入后 `idx` 只在书内唯一，跨典籍的键是 `<book>#<idx>`（`Poem.uid`），本表不参与那条链路 |

| `idx` | 该句在本篇内的序号 |
| `stanza` / `line` | 原书的章号 / 章内句号 |
| `clause` | 该句汉字串（已繁简归一） |
| `rhyme_chars` | 韵脚字，**可能不在句末**，也可能一句两个 |
| `rhyme_pos` | 韵脚字在句内的位置（1 起） |
| `rhyme_ids` | 形如 `12-a`：第 12 篇的局部韵标 `a` |

## 两个必须知道的读法约束

1. **局部韵标在每一章内重新起用。** 同一篇里第一章的 `a` 和第二章的 `a`
   不是同一个韵。归并必须按 `(poem, stanza, 标签)` 三元组，
   `ancient.rhyme_classes()` 即如此实现。
2. **不要用它做并查集式的全局韵部归并。** 取传递闭包会因少数"合韵"桥字
   把绝大多数韵脚字连成一个 1600+ 字的巨簇——这不是分部结果，是方法失效的
   信号。本模块因此只报告逐篇韵式与直接互押字对；全局韵部定名需要另一份
   带许可的逐字分部表（如王力三十部字表），目前仓库里没有，也不凭记忆编造。

引用请回到原书与上述 CLDF 数据集，不要只引本仓库。
