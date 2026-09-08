import { gfmFootnoteFromMarkdown } from 'mdast-util-gfm-footnote';
import { gfmStrikethroughFromMarkdown } from 'mdast-util-gfm-strikethrough';
import { gfmTableFromMarkdown } from 'mdast-util-gfm-table';
import { gfmTaskListItemFromMarkdown } from 'mdast-util-gfm-task-list-item';
import { gfmFootnote } from 'micromark-extension-gfm-footnote';
import { gfmStrikethrough } from 'micromark-extension-gfm-strikethrough';
import { gfmTable } from 'micromark-extension-gfm-table';
import { gfmTaskListItem } from 'micromark-extension-gfm-task-list-item';
import type { Processor } from 'unified';
import type {} from 'remark-parse';

/**
 * Parse-only GFM, excluding autolink literals whose import-time lookbehind
 * breaks Safari 16.0–16.3 (#144). Bare URLs/emails stay text; explicit Markdown
 * and angle-bracket links still work. Keep these imports separate: importing
 * remark-gfm or mdast-util-gfm would reintroduce the incompatible module.
 * There is no Markdown serialization consumer here.
 */
export default function remarkGfmNoAutolink(this: Processor): undefined {
  const data = this.data();
  const syntax = data.micromarkExtensions || (data.micromarkExtensions = []);
  const trees = data.fromMarkdownExtensions || (data.fromMarkdownExtensions = []);
  syntax.push(gfmFootnote(), gfmStrikethrough(), gfmTable(), gfmTaskListItem());
  trees.push(
    gfmFootnoteFromMarkdown(),
    gfmStrikethroughFromMarkdown(),
    gfmTableFromMarkdown(),
    gfmTaskListItemFromMarkdown(),
  );
}
