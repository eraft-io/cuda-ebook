#!/usr/bin/env python3
"""将 .tex 文件中的长文本行按指定字符数智能换行
- 先解包已断行的段落（合并连续行）
- 再用大括号感知的智能折行重新包装
- 去除连续重复行
"""

import sys
import os
import re
import glob


WIDTH = 60

SKIP_PREFIXES = (
    '\\section', '\\subsection', '\\subsubsection',
    '\\begin', '\\end', '\\appendix',
    '\\usepackage', '\\documentclass', '\\input',
    '\\title', '\\author', '\\date',
    '\\maketitle', '\\tableofcontents',
    '\\newcommand', '\\renewcommand',
    '\\includegraphics',
    '\\caption', '\\label', '\\ref', '\\eqref',
    '\\centering', '\\float',
    '\\item', '\\bibitem',
    '\\hline', '\\toprule', '\\midrule', '\\bottomrule',
    '\\vspace', '\\hspace',
    '\\newpage', '\\clearpage',
    '\\par', '\\noindent',
    '\\makeatletter', '\\makeatother',
    '\\counterwithin',
    '\\lstset', '\\lstinputlisting',
    '\\definecolor',
    '\\hypersetup',
    '\\tcbset',
    '\\small', '\\large', '\\Large', '\\LARGE',
    '\\normalsize', '\\footnotesize', '\\scriptsize',
    '\\tiny',
    '\\href',
)


def should_skip(line):
    s = line.strip()
    if not s:
        return True
    if s.startswith('%'):
        return True
    for p in SKIP_PREFIXES:
        if s.startswith(p):
            return True
    if '&' in s and s.endswith('\\\\'):
        return True
    return False


def find_smart_break(line, width):
    """在 width 附近找到不破坏 LaTeX 大括号的断行位置"""
    # 优先在前向搜索
    for pos in range(width, 0, -1):
        if pos >= len(line):
            continue
        # 断点必须在空格处或中文字符间
        if line[pos] == ' ':
            seg = line[:pos]
            if seg.count('{') == seg.count('}'):
                # 不要在反斜杠命令前断行
                rest = line[pos:].lstrip(' ')
                if not rest.startswith('\\'):
                    return pos
        elif pos > 0 and line[pos - 1] != ' ' and line[pos] != ' ':
            # 中文无空格断行：检查断点后字符是否适合
            seg = line[:pos]
            if seg.count('{') == seg.count('}'):
                # 避免在反斜杠命令中间断开，也避免在裸露反斜杠后断开
                if not re.search(r'\\[a-zA-Z]*$', seg):
                    # 不要在反斜杠命令前断行
                    if line[pos] != '\\':
                        return pos

    # 如果前向没找到，尝试后向搜索（最多 width + 30）
    for pos in range(width, min(len(line), width + 30)):
        if line[pos] == ' ':
            seg = line[:pos]
            if seg.count('{') == seg.count('}'):
                rest = line[pos:].lstrip(' ')
                if not rest.startswith('\\'):
                    return pos
        elif pos > 0 and line[pos - 1] != ' ' and line[pos] != ' ':
            seg = line[:pos]
            if seg.count('{') == seg.count('}'):
                if not re.search(r'\\[a-zA-Z]*$', seg):
                    if line[pos] != '\\':
                        return pos

    # 实在找不到合适的断点，不断行
    return None


def wrap(line, width):
    """智能折行，不破坏 LaTeX 命令"""
    if len(line) <= width:
        return [line]

    result = []
    while len(line) > width:
        break_pos = find_smart_break(line, width)
        if break_pos is None:
            # 无法安全断行，输出整行
            result.append(line)
            break

        result.append(line[:break_pos])
        # 如果断点处是空格，跳过空格
        if break_pos < len(line) and line[break_pos] == ' ':
            line = line[break_pos + 1:]
        else:
            line = line[break_pos:]

    if line:
        result.append(line)

    return result


def unwrap_paragraphs(lines):
    """将已断行的段落合并为单行（用于重新包装前的预处理）"""
    result = []
    in_env = False
    pending = None

    for raw_line in lines:
        line = raw_line.rstrip('\n')
        stripped = line.strip()

        # 追踪 verbatim/lstlisting 环境
        if '\\begin{verbatim}' in stripped or '\\begin{lstlisting}' in stripped:
            if pending is not None:
                result.append(pending)
                pending = None
            in_env = True
            result.append(line)
            continue
        if '\\end{verbatim}' in stripped or '\\end{lstlisting}' in stripped:
            in_env = False
            result.append(line)
            continue

        if in_env:
            result.append(line)
            continue

        # 空行：输出 pending 并保留空行
        if not stripped:
            if pending is not None:
                result.append(pending)
                pending = None
            result.append(line)
            continue

        # should_skip 的行保持原样
        if should_skip(line):
            if pending is not None:
                result.append(pending)
                pending = None
            result.append(line)
            continue

        # 普通文本行：合并到 pending
        if pending is None:
            pending = line
        else:
            # 智能合并：判断是否需要插入空格
            if (pending.endswith(' ') or pending.endswith('{')
                    or line.startswith('}')):
                pending = pending + line
            elif (re.search(r'\\[a-zA-Z]+$', pending)
                    and re.match(r'^[a-zA-Z]+\{', line)):
                # 命令名被断开: \tex + tbf{ → \textbf{
                pending = pending + line
            elif (re.search(r'\\ $', pending)
                    and re.match(r'^[a-zA-Z]', line)):
                # \空格 + 命令延续: \ lstinline → \lstinline
                pending = pending.rstrip(' ') + line
            else:
                pending = pending + ' ' + line

    if pending is not None:
        result.append(pending)

    return result


def dedup_lines(lines):
    """去除连续重复的非空行"""
    result = []
    prev = None
    dup_count = 0
    for line in lines:
        stripped = line.strip()
        if stripped and stripped == prev:
            dup_count += 1
            continue
        result.append(line)
        prev = stripped if stripped else None
    return result, dup_count


def fix_broken_words(lines):
    """修复跨行断开的英文单词"""
    result = []
    i = 0
    while i < len(lines):
        if i + 1 < len(lines):
            raw = lines[i].rstrip('\n')
            nxt = lines[i+1].rstrip('\n')
            if raw and nxt:
                # 行尾是英文字母，下行首也是英文字母
                if (raw[-1].isascii() and raw[-1].isalpha()
                        and nxt[0].isascii() and nxt[0].isalpha()):
                    end_match = re.search(r'([a-zA-Z]+)$', raw)
                    start_match = re.match(r'^([a-zA-Z]+)', nxt)
                    if end_match and start_match:
                        left = end_match.group(1)
                        right = start_match.group(1)
                        # 确认是单词断行而非LaTeX命令
                        pre_pos = len(raw) - len(left)
                        if pre_pos == 0 or (pre_pos > 0 and (
                                not raw[pre_pos-1].isascii()
                                or raw[pre_pos-1] == ' '
                                or raw[pre_pos-1] in '{}('
                                or raw[pre_pos-1] in '$')):
                            after_pos = len(right)
                            if after_pos >= len(nxt) or (
                                    not nxt[after_pos].isascii()
                                    or nxt[after_pos] == ' '
                                    or nxt[after_pos] in '){},;:.!?$'):
                                if not re.search(r'\\[a-zA-Z]*$', raw[:pre_pos]):
                                    joined = raw + nxt
                                    # 只在合并后行不超过 WIDTH*2 时才合并
                                    if len(joined) <= WIDTH * 2:
                                        result.append(joined + '\n')
                                        i += 2
                                        continue
        result.append(lines[i])
        i += 1
    return result


def fix_broken_latex_commands(content):
    """修复跨行断开的LaTeX命令：\\ + 换行 + 命令名 → \\命令名
    注意：排除已知的短命令（如 \mu \to \a 等）避免误合并"""
    # 已知的短LaTeX命令（2个字母及以下），这些不应被合并
    SHORT_CMDS = {
        'a', 'b', 'c', 'd', 'i', 'j', 'k', 'l', 'o', 'r', 't', 'u',
        'mu', 'nu', 'pi', 'xi', 'to', 'or', 'if', 'in', 'le', 'ge',
        'pm', 'mp', 'ne', 'le', 'ge', 'cd', 'bf', 'it', 'rm', 'sf',
        'tt', 'sl', 'sc', 'em',
    }

    lines = content.split('\n')
    result = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        if i + 1 < len(lines):
            # 行尾以反斜杠结束，下行以字母开头
            m = re.search(r'\\([a-zA-Z]*)$', raw)
            nxt = lines[i + 1].lstrip()
            m2 = re.match(r'^([a-zA-Z]+)', nxt) if nxt else None
            if (m and m2
                    and not m.group(1)  # 行尾只有反斜杠，没有字母
                    and m2.group(1) not in SHORT_CMDS):
                # 合并两行
                lines[i + 1] = raw + nxt
                i += 1
                continue
        result.append(lines[i])
        i += 1

    # 修复反斜杠空格+命令名
    content = '\n'.join(result)
    content = re.sub(r'\\ +([a-zA-Z])', r'\\\1', content)
    return content


def rewrap_lines(lines, width):
    """重新折行超过 width 的行"""
    result = []
    in_env = False
    for line in lines:
        stripped = line.rstrip('\n')
        if '\\begin{verbatim}' in stripped or '\\begin{lstlisting}' in stripped:
            in_env = True
        if '\\end{verbatim}' in stripped or '\\end{lstlisting}' in stripped:
            in_env = False
        if in_env or should_skip(stripped) or len(stripped) <= width:
            result.append(line)
        else:
            parts = wrap(stripped, width)
            result.extend(parts)
    return result


def process_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # 第一步：解包段落（合并已断行的连续行）
    unwrapped = unwrap_paragraphs(lines)

    # 第二步：重新包装
    in_env = False
    output = []
    wrapped_count = 0

    for line in unwrapped:
        stripped = line.strip()

        if '\\begin{verbatim}' in stripped or '\\begin{lstlisting}' in stripped:
            in_env = True
        if '\\end{verbatim}' in stripped or '\\end{lstlisting}' in stripped:
            in_env = False

        if in_env or should_skip(line):
            output.append(line)
        else:
            parts = wrap(line, WIDTH)
            if len(parts) > 1:
                wrapped_count += 1
            output.extend(parts)

    # 第三步：去重
    output, dup_count = dedup_lines(output)

    # 第四步：修复断开的英文单词（单次，不重新折行）
    output = fix_broken_words(output)

    # 第五步：修复断开的LaTeX命令
    content = '\n'.join(output)
    if output:
        content += '\n'
    content = fix_broken_latex_commands(content)

    # 第六步：修复 $\\命令 跨行断开
    content = re.sub(r'(\$\\)\n(\n*)([a-zA-Z])', r'\1\3', content)
    content = re.sub(r'(\$\\[a-zA-Z]+[^\n]*)\n+', r'\1\n', content)

    # 第七步：最终去重
    lines_final = content.split('\n')
    deduped = []
    prev = None
    for line in lines_final:
        stripped = line.strip()
        if stripped and stripped == prev and len(stripped) > 5:
            continue
        deduped.append(line)
        prev = stripped if stripped else None
    content = '\n'.join(deduped)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

    out_count = content.count('\n')
    return out_count, wrapped_count, dup_count


def main():
    if len(sys.argv) > 1:
        files = sys.argv[1:]
    else:
        files = sorted(glob.glob('ch*.tex'))

    total_wrapped = 0
    total_dups = 0
    for f in files:
        if not os.path.exists(f):
            print(f'  跳过（不存在）: {f}')
            continue
        out_lines, wrapped, dups = process_file(f)
        total_wrapped += wrapped
        total_dups += dups
        status = ''
        if dups > 0:
            status = f', 去重 {dups}'
        if wrapped > 0:
            status += f', 折行 {wrapped}'
        print(f'  {f}: {out_lines} 行{status}')

    print(f'\n完成：{len(files)} 文件, 折行 {total_wrapped}, 去重 {total_dups}')


if __name__ == '__main__':
    main()
