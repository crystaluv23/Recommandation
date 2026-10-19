# Streaming JSON reader

An internal standard-library reader supports existing large local price archives.
It decodes one value at a time with a caller-selected JSONDecoder. Research's
existing _StreamingJSONReader name remains an alias; normal decoding behavior is
preserved. Evaluation label admission supplies strict decoding, ASCII JSON whitespace and
requires end of input (including rejection of trailing commas/content). Dataset
callers retain their original whitespace behavior by default. Optional SHA256 accumulates the exact UTF8 bytes consumed from the same
open stream, including original newline bytes, so parsing and hash verification
cannot refer to different archive contents. No cache, business schema, source
qualification or network access is added.
