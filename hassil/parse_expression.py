from dataclasses import dataclass
from typing import Optional, Union, List

from .expression import (
    Sentence,
    Sequence,
    SequenceType,
    Expression,
    TextChunk,
    RuleReference,
    ListReference,
)
from .parser import (
    ParseChunk,
    ParseType,
    peek_type,
    remove_escapes,
    remove_delimiters,
    GROUP_START,
    GROUP_END,
    OPT_END,
    OPT_START,
    LIST_END,
    LIST_START,
    RULE_END,
    RULE_START,
    next_chunk,
)


@dataclass
class ParseMetadata:
    """Debug metadata for more helpful parsing errors."""

    file_name: str
    line_number: int
    intent_name: Optional[str] = None


class ParseExpressionError(Exception):
    def __init__(self, chunk: ParseChunk, metadata: Optional[ParseMetadata] = None):
        super().__init__()
        self.chunk = chunk
        self.metadata = metadata

    def __str__(self) -> str:
        return f"Error in chunk {self.chunk} at {self.metadata}"


def ensure_alternative(seq: Sequence):
    if seq.type != SequenceType.ALTERNATIVE:
        seq.type = SequenceType.ALTERNATIVE

        # Collapse items into a single group
        seq.items = [
            Sequence(
                type=SequenceType.GROUP,
                items=seq.items,
            )
        ]


def parse_group_or_alt(
    seq_chunk: ParseChunk, metadata: Optional[ParseMetadata] = None
) -> Sequence:
    seq = Sequence(type=SequenceType.GROUP)
    if seq_chunk.parse_type == ParseType.GROUP:
        seq_text = remove_delimiters(seq_chunk.text, GROUP_START, GROUP_END)
    elif seq_chunk.parse_type == ParseType.OPT:
        seq_text = remove_delimiters(seq_chunk.text, OPT_START, OPT_END)
    else:
        raise ParseExpressionError(seq_chunk, metadata=metadata)

    item_chunk = next_chunk(seq_text)
    last_seq_text = seq_text

    while item_chunk is not None:
        if item_chunk.parse_type in {
            ParseType.WORD,
            ParseType.GROUP,
            ParseType.OPT,
            ParseType.SLOT,
            ParseType.RULE,
        }:
            item = parse_expression(item_chunk, metadata=metadata)

            if seq.type == SequenceType.ALTERNATIVE:
                # Add to most recent group
                if not seq.items:
                    seq.items.append(Sequence(type=SequenceType.GROUP))

                # Must be group or alternative
                last_item = seq.items[-1]
                if not isinstance(last_item, Sequence):
                    raise ParseExpressionError(seq_chunk, metadata=metadata)

                last_item.items.append(item)
            else:
                # Add to parent group
                seq.items.append(item)
        elif item_chunk.parse_type == ParseType.ALT:
            ensure_alternative(seq)

            # Begin new group
            seq.items.append(Sequence(type=SequenceType.GROUP))
        else:
            raise ParseExpressionError(seq_chunk, metadata=metadata)

        # Next chunk
        seq_text = seq_text[item_chunk.end_index :]
        seq_text = seq_text.lstrip()

        if seq_text == last_seq_text:
            raise ParseExpressionError(seq_chunk, metadata=metadata)

        item_chunk = next_chunk(seq_text)
        last_seq_text = seq_text

    return seq


def parse_expression(
    chunk: ParseChunk, metadata: Optional[ParseMetadata] = None
) -> Expression:
    if chunk.parse_type == ParseType.WORD:
        return TextChunk(text=chunk.text)

    if chunk.parse_type == ParseType.GROUP:
        return parse_group_or_alt(chunk, metadata=metadata)

    if chunk.parse_type == ParseType.OPT:
        seq = parse_group_or_alt(chunk, metadata=metadata)
        ensure_alternative(seq)
        seq.items.append(TextChunk(text=""))
        return seq

    if chunk.parse_type == ParseType.LIST:
        return ListReference(
            list_name=remove_delimiters(chunk.text, LIST_START, LIST_END),
        )

    if chunk.parse_type == ParseType.RULE:
        rule_name = remove_delimiters(
            chunk.text,
            RULE_START,
            RULE_END,
        )

        return RuleReference(rule_name=rule_name)

    raise ParseExpressionError(chunk, metadata=metadata)
