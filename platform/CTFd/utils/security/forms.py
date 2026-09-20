"""Bound accumulated form fields independently of streamed file uploads.

Werkzeug 2.3's decoder limit bounds its current buffer, not all field chunks.
Count field bytes across chunks and across fields before retaining their data.
This can be removed when upgrading to a parser that enforces an aggregate limit.
"""

from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.formparser import FormDataParser, MultiPartParser
from werkzeug.sansio.multipart import (
    Data, Epilogue, Field, File, MultipartDecoder, NeedData,
)


class BoundedMultipartParser(MultiPartParser):
    def parse(self, stream, boundary, content_length):
        decoder = MultipartDecoder(
            boundary,
            max_form_memory_size=self.max_form_memory_size,
            max_parts=self.max_form_parts,
        )
        fields, files, opened = [], [], []
        field_bytes = 0
        part = None
        try:
            while True:
                chunk = stream.read(self.buffer_size)
                decoder.receive_data(chunk or None)
                while True:
                    event = decoder.next_event()
                    if isinstance(event, (NeedData, Epilogue)):
                        break
                    if isinstance(event, Field):
                        part, value = event, bytearray()
                    elif isinstance(event, File):
                        part = event
                        output = self.start_file_streaming(event, content_length)
                        opened.append(output)
                    elif isinstance(event, Data):
                        if isinstance(part, Field):
                            field_bytes += len(event.data)
                            if (
                                self.max_form_memory_size is not None
                                and field_bytes > self.max_form_memory_size
                            ):
                                raise RequestEntityTooLarge()
                            value.extend(event.data)
                            if not event.more_data:
                                fields.append((part.name, value.decode(
                                    self.get_part_charset(part.headers), self.errors,
                                )))
                        elif isinstance(part, File):
                            output.write(event.data)
                            if not event.more_data:
                                output.seek(0)
                                files.append((part.name, FileStorage(
                                    output, part.filename, part.name, headers=part.headers,
                                )))
                        else:
                            raise ValueError("Multipart data without a part")
                if not chunk:
                    return self.cls(fields), self.cls(files)
        except BaseException:
            for output in opened:
                output.close()
            raise


class BoundedFormDataParser(FormDataParser):
    def _parse_multipart(self, stream, mimetype, content_length, options):
        boundary = options.get("boundary", "").encode("ascii")
        if not boundary:
            raise ValueError("Missing boundary")
        parser = BoundedMultipartParser(
            stream_factory=self.stream_factory,
            max_form_memory_size=self.max_form_memory_size,
            max_form_parts=self.max_form_parts,
            cls=self.cls,
        )
        form, files = parser.parse(stream, boundary, content_length)
        return stream, form, files
