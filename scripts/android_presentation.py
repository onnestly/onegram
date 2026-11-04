from pathlib import Path
import re, math, os
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen

def wordmark():
    font = TTFont(os.environ.get('ONEGRAM_WORDMARK_FONT', str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/seguisb.ttf')))
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    positions = []
    advance = 0
    low = 10 ** 9
    high = -10 ** 9
    for char in 'OneGram':
        glyph = glyphs[cmap[ord(char)]]
        bounds = BoundsPen(glyphs)
        glyph.draw(bounds)
        if bounds.bounds:
            low = min(low, bounds.bounds[1])
            high = max(high, bounds.bounds[3])
        positions.append((glyph, advance))
        advance += glyph.width
    scale = 52 / (high - low)
    pen = SVGPathPen(glyphs)
    for glyph, x in positions:
        glyph.draw(TransformPen(pen, (scale, 0, 0, -scale, 3 + x * scale, 3 + high * scale)))
    width = math.ceil(advance * scale + 6)
    return f'<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="90dp" android:height="22dp" android:viewportWidth="{width}" android:viewportHeight="58"><path android:fillColor="#FFFFFFFF" android:pathData="{pen.getCommands()}"/></vector>'

def apply_presentation(decoded: Path):
    for name in ['telegram_logo', 'telegram_logo_2']:
        target = decoded / 'res/drawable-anydpi-v24' / f'{name}.xml'
        target.write_text(wordmark(), encoding='utf-8')
    foreground = '<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="108dp" android:height="108dp" android:viewportWidth="128" android:viewportHeight="128"><path android:fillColor="#F8FBFF" android:pathData="M18,59 L45,63 L63,43 L79,61 L108,54 L90,83 L35,85 Z"/><path android:fillColor="#DCE8F7" android:pathData="M18,59 L65,72 L35,85 Z M63,43 L65,72 L79,61 Z"/><path android:fillColor="#B4CDEB" android:pathData="M35,85 L65,72 L90,83 Z"/><path android:fillColor="#EEF5FD" android:pathData="M65,72 L108,54 L90,83 Z"/></vector>'
    drawable = decoded / 'res/drawable'
    drawable.mkdir(exist_ok=True)
    (drawable / 'onegram_icon_foreground.xml').write_text(foreground, encoding='utf-8')
    (drawable / 'onegram_icon_background.xml').write_text('<shape xmlns:android="http://schemas.android.com/apk/res/android" android:shape="rectangle"><solid android:color="#238CE6"/></shape>', encoding='utf-8')
    mipmap = decoded / 'res/mipmap-anydpi-v26'
    mipmap.mkdir(exist_ok=True)
    (mipmap / 'onegram_icon.xml').write_text('<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android"><background android:drawable="@drawable/onegram_icon_background"/><foreground android:drawable="@drawable/onegram_icon_foreground"/></adaptive-icon>', encoding='utf-8')
    path = next(decoded.glob('smali*/org/telegram/ui/Cells/v3.smali'))
    s = path.read_text(encoding='utf-8')
    if 'onegramSettingsHeaderMeasure' not in s:
        pattern = '(?m)^\\.method public final onMeasure\\(II\\)V$'
        if not re.search(pattern, s):
            raise RuntimeError('Native account section header changed')
        s = re.sub(pattern, '.method private onegramSettingsHeaderMeasure(II)V', s, count=1)
        s += '\n.method public final onMeasure(II)V\n    .locals 3\n    invoke-direct {p0, p1, p2}, Lorg/telegram/ui/Cells/v3;->onegramSettingsHeaderMeasure(II)V\n    invoke-static {p0}, Lorg/onegram/OneGramUi;->settingsHeaderExtra(Landroid/view/View;)I\n    move-result v0\n    if-eqz v0, :onegram_settings_header_done\n    invoke-virtual {p0}, Landroid/view/View;->getMeasuredWidth()I\n    move-result v1\n    invoke-virtual {p0}, Landroid/view/View;->getMeasuredHeight()I\n    move-result v2\n    add-int/2addr v2, v0\n    invoke-virtual {p0, v1, v2}, Landroid/view/View;->setMeasuredDimension(II)V\n    :onegram_settings_header_done\n    return-void\n.end method\n'
        if re.search('(?m)^\\.method[^\\n]* onLayout\\(ZIIII\\)V$', s):
            s = re.sub('(?m)^\\.method[^\\n]* onLayout\\(ZIIII\\)V$', '.method private onegramSettingsHeaderLayout(ZIIII)V', s, count=1)
            call = 'invoke-direct/range {p0 .. p5}, Lorg/telegram/ui/Cells/v3;->onegramSettingsHeaderLayout(ZIIII)V'
        else:
            call = 'invoke-super/range {p0 .. p5}, Landroid/widget/FrameLayout;->onLayout(ZIIII)V'
        s += '\n.method public onLayout(ZIIII)V\n    .locals 0\n    ' + call + '\n    invoke-static {p0}, Lorg/onegram/OneGramUi;->layoutSettingsHeader(Landroid/view/View;)V\n    return-void\n.end method\n'
        path.write_text(s, encoding='utf-8')
    path = next(decoded.glob('smali*/org/telegram/ui/Cells/s2.smali'))
    s = path.read_text(encoding='utf-8')
    if 'OneGramUi;->prepareIgnoredCellAfterLayout' not in s:
        start = s.index('.method private onegramOriginalonDraw(')
        end = s.index('.end method', start)
        body = s[start:end]
        match = re.search('(?m)^    iget-boolean [^\\n]*Lorg/telegram/ui/Cells/s2;->F3:Z$', body)
        if not match:
            raise RuntimeError('Native unread badge paint hook missing')
        body = body[:match.start()] + '    invoke-static/range {p0 .. p0}, Lorg/onegram/OneGramUi;->prepareIgnoredCellAfterLayout(Landroid/view/View;)V\n' + body[match.start():]
        path.write_text(s[:start] + body + s[end:], encoding='utf-8')
