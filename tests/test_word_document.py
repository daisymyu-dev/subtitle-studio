"""Offline Word export contracts; all caption text here is self-authored."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
import importlib
import io
import os
from pathlib import Path
import tempfile
import traceback
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from docx import Document as open_document
from docx.document import Document as PythonDocument


try:
    word_document = importlib.import_module('studio.word_document')
except ModuleNotFoundError as error:
    if error.name != 'studio.word_document':
        raise
    word_document = None

ROOT = Path(__file__).resolve().parents[1]
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
W = '{' + NS['w'] + '}'


def sample_blocks(count=1):
    return [dict(start=index * 3.0, end=index * 3.0 + 2.5,
                 english=f'Original English sentence {index + 1}.',
                 chinese=f'自己编写的中文句子 {index + 1}。')
            for index in range(count)]


def document_xml(path, member='word/document.xml'):
    with ZipFile(path) as archive:
        return ET.fromstring(archive.read(member))


def paragraphs(root):
    return [''.join(p.itertext()) for p in root.findall('w:body/w:p', NS)]


class WordTestCase(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(word_document, 'studio.word_document is not implemented')
        temporary_root = ROOT / '.work' / 'tmp'
        temporary_root.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix='word-test-', dir=temporary_root)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write_document(self, destination=None, **changes):
        options = dict(title='Self authored bilingual reading',
                       url='https://example.test/watch?v=offline&source=qa',
                       blocks=sample_blocks(),
                       source_note='自己编写的中文 不是网络翻译',
                       english_note='Self authored English not platform captions')
        options.update(changes)
        return word_document.write_word_document(
            destination or self.root / 'reading.docx', **options)


class WordDocumentTests(WordTestCase):
    def test_sentence_fragments_are_labeled_without_changing_english(self):
        blocks=sample_blocks();blocks[0]['fragment']=True
        result=self.write_document(blocks=blocks)
        body=paragraphs(document_xml(result))
        self.assertTrue(any('残句' in text for text in body))
        self.assertIn(blocks[0]['english'],body)
    def test_exact_destination_not_a_filename_derived_from_title(self):
        destination = self.root / 'nested' / 'exact name.docx'
        title = '../CON:<unsafe> "title"? & 中文'
        result = self.write_document(destination, title=title)
        self.assertIsInstance(result, Path)
        self.assertEqual(result, destination)
        self.assertEqual(list(self.root.rglob('*.docx')), [destination])
        self.assertEqual(paragraphs(document_xml(result))[0], title)
        with ZipFile(result) as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn('[Content_Types].xml', archive.namelist())
            self.assertIn('word/styles.xml', archive.namelist())

    def test_retains_all_237_blocks_in_time_english_chinese_order(self):
        blocks = sample_blocks(237)
        result = self.write_document(blocks=blocks)
        body = paragraphs(document_xml(result))
        expected = []
        for index, block in enumerate(blocks):
            start = index * 3
            end = start + 2
            expected.extend([
                f'{start // 3600:02}:{start // 60 % 60:02}:{start % 60:02}.000'
                f' --> {end // 3600:02}:{end // 60 % 60:02}:{end % 60:02}.500',
                block['english'], block['chinese'],
            ])
        self.assertEqual(body[-len(expected):], expected)
        self.assertEqual(len(body), 4 + 237 * 3)

    def test_unicode_xml_literals_and_provenance_are_not_interpreted(self):
        title = '中文 café 🚀 <w:p> & "quoted"'
        english = 'Use <name> &amp; "quotes" — café 🚀.'
        chinese = '保留 <标签> 和 & 符号，不把 &amp; 当作实体。'
        url = 'https://example.test/?a=1&b=<literal>'
        source_note = '中文来源 <local> & self authored'
        english_note = 'English source <local> & self authored'
        result = self.write_document(
            title=title, url=url, source_note=source_note, english_note=english_note,
            blocks=[dict(start=.9996, end=3600.001, english=english, chinese=chinese)])
        body = paragraphs(document_xml(result))
        self.assertEqual(body[0], title)
        self.assertEqual(body[:4], [title, f'来源链接：{url}',
                                    f'英文来源：{english_note}', f'中文来源：{source_note}'])
        for value in (url, source_note, english_note):
            self.assertTrue(any(value in paragraph for paragraph in body))
        self.assertEqual(body[-3:], ['00:00:01.000 --> 01:00:00.001', english, chinese])

    def test_a4_black_title_readable_body_and_page_number_footer(self):
        result = self.write_document()
        root = document_xml(result)
        size = root.find('w:body/w:sectPr/w:pgSz', NS)
        self.assertEqual((size.get(W + 'w'), size.get(W + 'h')), ('11906', '16838'))
        self.assertIn(size.get(W + 'orient'), (None, 'portrait'))
        title = root.find('w:body/w:p', NS)
        self.assertEqual(title.find('w:pPr/w:pStyle', NS).get(W + 'val'), 'Title')
        self.assertIsNone(title.find('w:pPr/w:pBdr', NS))
        styles = document_xml(result, 'word/styles.xml')
        title_styles = styles.findall("w:style[@w:styleId='Title']", NS)
        self.assertEqual(len(title_styles), 1)
        title_style = title_styles[0]
        title_color = title_style.find('w:rPr/w:color', NS)
        self.assertIsNotNone(title_color)
        self.assertEqual(title_color.get(W + 'val'), '000000')
        self.assertIsNone(title_style.find('w:pPr/w:pBdr', NS))
        self.assertGreaterEqual(int(styles.find('w:docDefaults/w:rPrDefault/w:rPr/w:sz', NS)
                                    .get(W + 'val')), 22)
        self.assertEqual(root.findall('.//w:tbl', NS), [])
        self.assertIsNotNone(root.find('w:body/w:sectPr/w:footerReference', NS))
        with ZipFile(result) as archive:
            footer_names = [name for name in archive.namelist()
                            if name.startswith('word/footer') and name.endswith('.xml')]
            self.assertTrue(footer_names)
            footer = ET.fromstring(archive.read(footer_names[0]))
        instructions = [node.text.strip() for node in footer.findall('.//w:instrText', NS)]
        self.assertIn('PAGE', instructions)

    def test_multiline_text_uses_word_breaks_without_losing_lines(self):
        blocks = [dict(start=0, end=2, english='First line.\nSecond line.\tEnd.',
                       chinese='第一行。\r\n第二行。')]
        result = self.write_document(blocks=blocks)
        root = document_xml(result)
        body = root.findall('w:body/w:p', NS)
        self.assertEqual(''.join(body[-2].itertext()), 'First line.Second line.End.')
        self.assertEqual(len(body[-2].findall('.//w:br', NS)), 1)
        self.assertEqual(len(body[-2].findall('.//w:tab', NS)), 1)
        self.assertEqual(len(body[-1].findall('.//w:br', NS)), 1)

    def test_rejects_non_docx_destination_without_creating_a_directory(self):
        destination = self.root / 'not-created' / 'output.txt'
        with self.assertRaises(ValueError):
            self.write_document(destination)
        self.assertFalse(destination.parent.exists())

    def test_rejects_empty_or_incomplete_blocks_not_a_partial_success(self):
        invalid = [[], [dict(start=0, end=1, english='Original')],
                   [dict(start=0, end=1, english='Original', chinese='  ')],
                   [dict(start=2, end=1, english='Original', chinese='中文')],
                   [dict(start=float('nan'), end=1, english='Original', chinese='中文')],
                   [dict(start=0, end=float('inf'), english='Original', chinese='中文')]]
        for blocks in invalid:
            with self.subTest(blocks=blocks), self.assertRaises(ValueError):
                self.write_document(blocks=blocks)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_rejects_invalid_xml_control_characters_before_serialization(self):
        with mock.patch.object(PythonDocument, 'save') as save:
            with self.assertRaises(ValueError):
                self.write_document(title='Invalid\x00title')
        save.assert_not_called()

    def test_builder_failure_preserves_existing_destination_and_does_not_leak_text(self):
        destination = self.root / 'existing.docx'
        destination.write_bytes(b'original bytes')
        secret_text = 'PRIVATE CAPTION NOT FOR ERROR MESSAGES'
        output = io.StringIO()
        with mock.patch.object(PythonDocument, 'save', side_effect=ValueError(secret_text)), \
                redirect_stdout(output), redirect_stderr(output):
            try:
                self.write_document(destination, title=secret_text)
            except RuntimeError as error:
                self.assertNotIn(secret_text, str(error))
                self.assertNotIn(secret_text, ''.join(traceback.format_exception(error)))
            else:
                self.fail('A failed serializer must not publish a document.')
        self.assertEqual(output.getvalue(), '')
        self.assertEqual(destination.read_bytes(), b'original bytes')
        self.assertEqual(list(self.root.iterdir()), [destination])

    def test_uses_python_docx_to_serialize_the_document_in_memory(self):
        real_save = PythonDocument.save
        with mock.patch.object(PythonDocument, 'save', autospec=True,
                               side_effect=real_save) as save:
            self.write_document()
        save.assert_called_once()
        self.assertIsInstance(save.call_args.args[1], io.BytesIO)

    def test_atomic_publish_failure_preserves_old_file_and_removes_staging(self):
        destination = self.write_document()
        original = destination.read_bytes()
        with mock.patch.object(word_document.os, 'replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                self.write_document(destination, title='Replacement document')
        self.assertEqual(destination.read_bytes(), original)
        self.assertEqual(list(self.root.iterdir()), [destination])

    def test_success_replaces_only_the_exact_destination_and_leaves_no_staging(self):
        destination = self.root / 'chosen.DOCX'
        destination.write_bytes(b'old output')
        result = self.write_document(str(destination))
        self.assertEqual(result, destination)
        self.assertEqual(paragraphs(document_xml(result))[0], 'Self authored bilingual reading')
        self.assertEqual(list(self.root.iterdir()), [destination])

    def test_serialization_failure_does_not_leave_a_partial_document(self):
        with mock.patch.object(PythonDocument, 'save', side_effect=OSError('PRIVATE CAPTION')):
            with self.assertRaises(RuntimeError) as raised:
                self.write_document()
        self.assertNotIn('PRIVATE CAPTION', str(raised.exception))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_invalid_builder_output_is_not_written_as_docx(self):
        def invalid_save(document, stream):
            stream.write(b'not a DOCX')

        with mock.patch.object(PythonDocument, 'save', autospec=True, side_effect=invalid_save):
            with self.assertRaises(RuntimeError):
                self.write_document()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_validation_does_not_mutate_or_summarize_input(self):
        blocks = sample_blocks(2)
        expected = [dict(block) for block in blocks]
        self.write_document(blocks=blocks)
        self.assertEqual(blocks, expected)

    def test_long_valid_title_is_not_truncated_or_rejected_by_metadata(self):
        title = '完整的自己编写的标题 café 🚀 ' * 30
        try:
            result = self.write_document(title=title)
        except RuntimeError:
            self.fail('A valid long title must not be rejected by core-property limits.')
        self.assertEqual(paragraphs(document_xml(result))[0], title)
        with ZipFile(result) as archive:
            properties = ET.fromstring(archive.read('docProps/core.xml'))
        self.assertEqual(properties.find('{http://purl.org/dc/elements/1.1/}title').text, title)

    def test_fonts_are_explicit_without_theme_overrides_or_duplicate_properties(self):
        result = self.write_document()
        styles = document_xml(result, 'word/styles.xml')
        for style_id in ('Normal', 'Title', 'Provenance', 'TimeRange', 'English', 'Chinese'):
            with self.subTest(style=style_id):
                style = styles.find(f"w:style[@w:styleId='{style_id}']", NS)
                self.assertIsNotNone(style)
                properties = style.find('w:rPr', NS)
                self.assertEqual(len(properties), len({node.tag for node in properties}))
                fonts = properties.find('w:rFonts', NS)
                self.assertEqual(fonts.attrib, {W + 'ascii': 'Arial', W + 'hAnsi': 'Arial',
                                               W + 'eastAsia': 'Microsoft YaHei', W + 'cs': 'Arial'})
                if style_id in ('Normal', 'English', 'Chinese'):
                    self.assertGreaterEqual(int(properties.find('w:sz', NS).get(W + 'val')), 22)

    def test_rejects_invalid_xml_in_every_text_field_before_serialization(self):
        with mock.patch.object(PythonDocument, 'save') as save:
            for field in ('title', 'url', 'source_note', 'english_note', 'english', 'chinese'):
                for invalid in ('\x00', '\x08', '\x0b', '\x0c', '\x1f',
                                '\ud800', '\udfff', '\ufffe', '\uffff'):
                    with self.subTest(field=field, codepoint=ord(invalid)):
                        changes = {field: 'Self authored ' + invalid}
                        if field in ('english', 'chinese'):
                            blocks = sample_blocks()
                            blocks[0].update(changes)
                            changes = dict(blocks=blocks)
                        with self.assertRaises(ValueError):
                            self.write_document(**changes)
        save.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_rejects_non_text_provenance_and_non_list_or_non_object_blocks(self):
        for field in ('title', 'url', 'source_note', 'english_note'):
            for value in (None, True, 42, [], {}, '', ' \t\r\n'):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.write_document(**{field: value})
        for blocks in (None, (), {}, 'not a list', [None], [True], ['not an object']):
            with self.subTest(blocks=blocks), self.assertRaises(ValueError):
                self.write_document(blocks=blocks)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_oversized_and_invalid_times_are_validation_errors_before_serialization(self):
        with mock.patch.object(PythonDocument, 'save') as save:
            for start, end in ((True, 2), (0, False), ('0', 2), (0, None), (-1, 2),
                               (0, 0), (0, float('nan')), (float('-inf'), 2),
                               (0, 10 ** 1000), (0, 1e308)):
                with self.subTest(start_type=type(start).__name__, end_type=type(end).__name__):
                    blocks = sample_blocks()
                    blocks[0].update(start=start, end=end)
                    try:
                        self.write_document(blocks=blocks)
                    except Exception as error:
                        self.assertIsInstance(error, ValueError)
                    else:
                        self.fail('Invalid times must not reach the document builder.')
        save.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_timestamp_rounding_is_half_up_with_second_minute_and_hour_carries(self):
        blocks = [dict(start=start, end=end, english='Original sentence.', chinese='原句。')
                  for start, end in ((.0005, .0015), (59.9995, 60.0015),
                                     (3599.9995, 3600.0015))]
        result = self.write_document(blocks=blocks)
        self.assertEqual(paragraphs(document_xml(result))[4::3], [
            '00:00:00.001 --> 00:00:00.002',
            '00:01:00.000 --> 00:01:00.002',
            '01:00:00.000 --> 01:00:00.002'])

    def test_round_trip_preserves_spaces_unicode_and_normalized_line_breaks(self):
        english = '  café e\u0301 🚀\r\nSecond\rThird\n\n\tLast.  '
        chinese = '\t中文 <标签> &amp;\r\n第二行。\t  '
        result = self.write_document(
            blocks=[dict(start=0, end=2, english=english, chinese=chinese)])
        document = open_document(result)
        self.assertEqual(document.paragraphs[-2].text,
                         english.replace('\r\n', '\n').replace('\r', '\n'))
        self.assertEqual(document.paragraphs[-1].text, chinese.replace('\r\n', '\n'))

    def test_uncertain_restored_tail_label_does_not_change_original_words(self):
        blocks = sample_blocks()
        blocks[0].update(fragment=True, fragment_reason='restored_tail_uncertain')
        body = paragraphs(document_xml(self.write_document(blocks=blocks)))
        self.assertEqual(body[-3:], ['00:00:00.000 --> 00:00:02.500  · 结尾完整性待核对',
                                    blocks[0]['english'], blocks[0]['chinese']])

    def test_staging_write_failure_preserves_destination_and_removes_partial_file(self):
        destination = self.root / 'existing.docx'
        destination.write_bytes(b'preserved original document')
        real_temporary_file = tempfile.NamedTemporaryFile

        class FailedWrite:
            def __init__(self, output):
                self.output = output
                self.name = output.name

            def __enter__(self):
                self.output.__enter__()
                return self

            def write(self, content):
                self.output.write(content[:20])
                raise OSError('Simulated disk failure')

            def __exit__(self, *args):
                return self.output.__exit__(*args)

        def failing_temporary_file(*args, **kwargs):
            return FailedWrite(real_temporary_file(*args, **kwargs))

        with mock.patch.object(word_document.tempfile, 'NamedTemporaryFile',
                               side_effect=failing_temporary_file):
            with self.assertRaises(OSError):
                self.write_document(destination)
        self.assertEqual(destination.read_bytes(), b'preserved original document')
        self.assertEqual(list(self.root.iterdir()), [destination])


class RuntimeTests(WordTestCase):
    def test_word_export_never_starts_node_or_another_external_process(self):
        with mock.patch('subprocess.run', side_effect=AssertionError(
                'Word export must work in-process without Node or Codex.')), \
                mock.patch('subprocess.Popen', side_effect=AssertionError(
                    'Word export must never launch a child process.')), \
                mock.patch('os.system', side_effect=AssertionError(
                    'Word export must never invoke a shell.')):
            result = self.write_document()
        self.assertEqual(paragraphs(document_xml(result))[-2:],
                         [sample_blocks()[0]['english'], sample_blocks()[0]['chinese']])

    def test_export_needs_neither_a_profile_runtime_nor_path_tools(self):
        absent = str(self.root / 'absent profile')
        with mock.patch.dict(os.environ, PATH='', HOME=absent, USERPROFILE=absent,
                             CODEX_HOME=absent), \
                mock.patch.object(Path, 'home', side_effect=AssertionError(
                    'Word export must not search the user profile.')):
            result = self.write_document()
        self.assertEqual(paragraphs(document_xml(result))[0], 'Self authored bilingual reading')

    def test_export_is_independent_of_a_frozen_app_extraction_directory(self):
        with mock.patch.object(word_document.sys, 'frozen', True, create=True), \
                mock.patch.object(word_document.sys, '_MEIPASS',
                                  str(self.root / 'absent bundle'), create=True), \
                mock.patch.object(Path, 'home', side_effect=AssertionError(
                    'Word export must not search for deployment tools.')):
            result = self.write_document()
        self.assertTrue(result.is_file())


class DesktopTests(WordTestCase):
    def source(self, name='reading.docx'):
        source = self.root / name
        source.write_bytes(b'local document bytes')
        return source

    def test_desktop_collisions_are_numbered_without_overwrite(self):
        source = self.source()
        desktop = self.root / 'redirected desktop'
        desktop.mkdir()
        (desktop / source.name).write_bytes(b'keep first')
        (desktop / 'reading (1).docx').write_bytes(b'keep second')
        result = word_document.save_to_desktop(source, desktop)
        self.assertIsInstance(result, Path)
        self.assertEqual(result, desktop / 'reading (2).docx')
        self.assertEqual(result.read_bytes(), source.read_bytes())
        self.assertEqual((desktop / source.name).read_bytes(), b'keep first')
        self.assertEqual((desktop / 'reading (1).docx').read_bytes(), b'keep second')

    def test_concurrent_saves_use_exclusive_creation(self):
        source = self.source()
        desktop = self.root / 'desktop'
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: word_document.save_to_desktop(source, desktop),
                                    range(8)))
        self.assertEqual(len(set(results)), 8)
        self.assertEqual(len(list(desktop.iterdir())), 8)
        self.assertTrue(all(path.read_bytes() == source.read_bytes() for path in results))

    def test_copy_failure_removes_only_its_new_partial_file(self):
        source = self.source()
        desktop = self.root / 'desktop'
        desktop.mkdir()
        original = desktop / source.name
        original.write_bytes(b'keep existing')

        def fail_mid_copy(reader, writer):
            writer.write(reader.read(4))
            raise OSError('self authored simulated disk failure')

        with mock.patch.object(word_document.shutil, 'copyfileobj', side_effect=fail_mid_copy):
            with self.assertRaises(OSError):
                word_document.save_to_desktop(source, desktop)
        self.assertEqual(list(desktop.iterdir()), [original])
        self.assertEqual(original.read_bytes(), b'keep existing')
        self.assertEqual(source.read_bytes(), b'local document bytes')

    def test_missing_source_does_not_create_a_desktop_file(self):
        desktop = self.root / 'desktop'
        with self.assertRaises(FileNotFoundError):
            word_document.save_to_desktop(self.root / 'absent.docx', desktop)
        self.assertFalse(desktop.exists())

    def test_close_failure_also_removes_new_partial_copy(self):
        source = self.source()
        desktop = self.root / 'desktop'
        real_open = Path.open

        class CloseFailure:
            def __init__(self, output):
                self.output = output

            def __enter__(self):
                return self.output

            def __exit__(self, *args):
                self.output.close()
                raise OSError('simulated flush or close failure')

        def open_with_failure(path, mode='r', *args, **kwargs):
            output = real_open(path, mode, *args, **kwargs)
            return CloseFailure(output) if mode == 'xb' else output

        with mock.patch.object(Path, 'open', autospec=True, side_effect=open_with_failure):
            with self.assertRaises(OSError):
                word_document.save_to_desktop(source, desktop)
        self.assertEqual(list(desktop.iterdir()), [])
        self.assertEqual(source.read_bytes(), b'local document bytes')

    def test_source_already_on_desktop_is_preserved(self):
        source = self.source()
        result = word_document.save_to_desktop(source, self.root)
        self.assertEqual(result, self.root / 'reading (1).docx')
        self.assertEqual(source.read_bytes(), b'local document bytes')
        self.assertEqual(result.read_bytes(), source.read_bytes())

    def test_windows_default_uses_os_desktop_instead_of_assumed_home(self):
        source = self.source()
        redirected = self.root / 'OneDrive redirected' / '桌面'

        def get_folder(window, folder, token, flags, buffer):
            self.assertEqual(folder, 0x0010)  # CSIDL_DESKTOPDIRECTORY, not virtual Desktop.
            buffer.value = str(redirected)
            return 0

        shell32 = mock.Mock()
        shell32.SHGetFolderPathW.side_effect = get_folder
        with mock.patch.object(word_document.sys, 'platform', 'win32'), \
                mock.patch.object(word_document.ctypes, 'windll', mock.Mock(shell32=shell32)):
            result = word_document.save_to_desktop(source)
        self.assertEqual(result, redirected / source.name)
        shell32.SHGetFolderPathW.assert_called_once()

    def test_os_desktop_lookup_failure_does_not_guess_or_copy(self):
        source = self.source()
        shell32 = mock.Mock()
        shell32.SHGetFolderPathW.return_value = -2147467259
        with mock.patch.object(word_document.sys, 'platform', 'win32'), \
                mock.patch.object(word_document.ctypes, 'windll', mock.Mock(shell32=shell32)):
            with self.assertRaises(OSError):
                word_document.save_to_desktop(source)
        self.assertEqual(list(self.root.iterdir()), [source])


if __name__ == '__main__':
    unittest.main()
