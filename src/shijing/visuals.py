"""字云 / 词云出图。

原版脚本硬编码 `font_path='simhei.ttf'` 并调用 `plt.show()`，在非 Windows、无显示
环境下直接崩。这里改成：跨平台找中文字体 + 一律落盘 PNG。
"""
from __future__ import annotations

from pathlib import Path

FONT_CANDIDATES = [
    # Windows
    'C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simhei.ttf', 'C:/Windows/Fonts/simsun.ttc',
    # Linux
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
    '/usr/share/fonts/truetype/arphic/uming.ttc',
    # macOS
    '/System/Library/Fonts/PingFang.ttc',
    '/Library/Fonts/Arial Unicode.ttf',
]


def find_font(explicit: str | None = None) -> str:
    """返回一个可用的中文字体路径。找不到就报清楚的下一步指引，而不是让 wordcloud 乱码。"""
    import shutil
    if explicit:
        if Path(explicit).exists():
            return explicit
        raise SystemExit(f'--font 指定的字体不存在：{explicit}（去掉 --font 可自动探测）')
    for cand in FONT_CANDIDATES:
        if Path(cand).exists():
            return cand
    found = shutil.which('fc-list')
    if found:
        import subprocess
        try:
            out = subprocess.run([found, ':lang=zh', 'file'],
                                 capture_output=True, text=True, timeout=10).stdout
            for line in out.splitlines():
                p = line.split(':')[0].strip()
                if p and Path(p).exists():
                    return p
        except Exception:  # noqa: BLE001 - 探测失败就走兜底提示
            pass
    raise SystemExit(
        '未找到可用中文字体，字云会渲染成方框。请安装 CJK 字体（如 fonts-noto-cjk）'
        '或用 --font 指定一个 .ttf/.ttc 路径。')


def make_cloud(freq: dict[str, int], out: str | Path, *, font: str | None = None,
               width: int = 1600, height: int = 900, max_words: int = 300,
               title: str = '') -> Path:
    """按词频出图并落盘。freq 必须是已繁简归一的汉字词条。"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from wordcloud import WordCloud

    wp = find_font(font)
    cloud = WordCloud(
        font_path=wp, width=width, height=height, background_color='white',
        max_words=max_words, prefer_horizontal=0.95, relative_scaling=0.5,
        colormap='Dark2', random_state=42).generate_from_frequencies(freq)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
    ax.imshow(cloud, interpolation='bilinear')
    ax.set_axis_off()
    if title:
        # 字体路径必须包成 FontProperties，直接传字符串会被当成字体族名解析而报错
        from matplotlib.font_manager import FontProperties
        ax.set_title(title, fontproperties=FontProperties(fname=wp), fontsize=16)
    fig.savefig(out, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return out
