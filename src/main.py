from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable, Generator


@dataclass
class Token:
    ty: str
    value: str
    start_index: int
    end_index: int


class EatFailed(Exception):
    def __init__(self, comment: str, /, failed_on_eof: bool) -> None:
        super().__init__(comment)
        self.failed_on_eof = failed_on_eof


class ParsingFailed(Exception):
    pass


class EOF:
    def __repr__(self) -> str:
        return "EOF"

    def __str__(self) -> str:
        return "EOF"


class CursorEater(ABC):
    text: str

    def __init__(self, text: str) -> None:
        self.text = text

    @abstractmethod
    def index(self) -> int:
        ...

    @abstractmethod
    def move(self, delta: int) -> None:
        ...

    def peek(self) -> str | EOF:
        return self.text[self.index()] if self.index() < len(self.text) else EOF()

    def eat_if(self, predicate: Callable[[str], bool], comment: str) -> str:
        chr = self.peek()
        if not isinstance(chr, EOF) and predicate(chr):
            # print(f"Eat: At index {self.index} '{chr}' while parsing {comment}")
            self.move(1)
            return chr

        # print(f"Raise EatFailed: At index {self.index} '{chr}' while parsing {comment}")
        raise EatFailed(f"At index {self.index()} '{chr}' while parsing {comment}", failed_on_eof=isinstance(chr, EOF))


@dataclass
class Frame:
    start_index: int
    end_index: int
    text: str

    @property
    def value(self) -> str:
        return self.text[self.start_index : self.end_index]

    @property
    def length(self) -> int:
        return self.end_index - self.start_index

    def token(self, ty: str) -> Token:
        return Token(ty, self.value, self.start_index, self.end_index)


class TransactionalCursor(CursorEater):
    frames: list[Frame]

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.frames = []

    def index(self) -> int:
        return self.frames[-1].end_index

    def move(self, delta: int) -> None:
        self.frames[-1].end_index += delta

    def commit(self) -> None:
        if len(self.frames) > 1:
            self.frames[-2].end_index = self.frames[-1].end_index
        self.frames.pop()

    def rollback(self) -> None:
        self.frames.pop()

    def begin(self) -> Frame:
        self.frames.append(Frame(self.index(), self.index(), self.text))
        return self.frames[-1]


# class FancyCursor(Cursor):
#     def token(self, ty: str) -> Token:
#         value = self.cursor.text[self.initial_index : self.cursor.index - self.initial_index]
#         return Token(ty, value, self.initial_index, self.cursor.index - 1)

#     def eat(self) -> str:
#         return self.eat_if(lambda _: True, "any char")

#     def eat_only(self, chr: str) -> str:
#         return self.eat_if(lambda c: c == chr, f"only '{chr}'")

#     def eat_any(self, lchr: str) -> str:
#         return self.eat_if(lambda c: c in lchr, f"any of '{lchr}'")


@contextmanager
def transaction(cursor: TransactionalCursor) -> Generator[Frame, None, None]:
    try:
        yield cursor.begin()
    except:
        cursor.rollback()
        raise

    cursor.commit()


@contextmanager
def guard(eof_only: bool = False) -> Generator[None, None, None]:
    try:
        yield
    except EatFailed as e:
        if e.failed_on_eof or not eof_only:
            pass
        else:
            raise


Parser = Callable[[Cursor], Token]


class ParserRegistry:
    parsers: list[Parser]

    def __init__(self) -> None:
        self.parsers = []

    def register(self, parser: Parser) -> Parser:
        print(f"Registering {parser}")
        self.parsers.append(parser)
        return parser


parser_registry = ParserRegistry()


@parser_registry.register
def p_str(cursor: Cursor) -> Token:
    with scoped(cursor) as scoped_cursor:
        quote = scoped_cursor.eat_any("'\"")
        with guard():
            while scoped_cursor.eat_if(lambda c: c != quote, f"anything but {quote}"):
                pass
        scoped_cursor.eat_only(quote)

    return scoped_cursor.token("STRING")


@parser_registry.register
def p_dot(cursor: Cursor) -> Token:
    with scoped(cursor) as scoped_cursor:
        scoped_cursor.eat_only(".")

    return scoped_cursor.token("DOT")


@parser_registry.register
def p_hex(cursor: Cursor) -> Token:
    with scoped(cursor) as scoped_cursor:
        scoped_cursor.eat_only("0")
        scoped_cursor.eat_only("x")
        scoped_cursor.eat_if(lambda c: c in "0123456789abcdefABCDEF", "hex digit")

        with guard():
            while scoped_cursor.eat_if(lambda c: c in "0123456789abcdefABCDEF", "hex digit"):
                pass

    return scoped_cursor.token("HEX")


@parser_registry.register
def p_bin(cursor: Cursor) -> Token:
    with scoped(cursor) as scoped_cursor:
        scoped_cursor.eat_only("0")
        scoped_cursor.eat_only("b")
        scoped_cursor.eat_if(lambda c: c in "01", "bin digit")

        with guard():
            while scoped_cursor.eat_if(lambda c: c in "01", "bin digit"):
                pass

    return scoped_cursor.token("BIN")


@parser_registry.register
def p_dec(cursor: Cursor) -> Token:
    with scoped(cursor) as scoped_cursor:
        scoped_cursor.eat_if(lambda c: c in "0123456789", "dec digit")

        with guard():
            while scoped_cursor.eat_if(lambda c: c in "0123456789", "dec digit"):
                pass

        if scoped_cursor.peek() == ".":
            scoped_cursor.eat_only(".")
            scoped_cursor.eat_if(lambda c: c in "0123456789", "dec digit")
            with guard():
                while scoped_cursor.eat_if(lambda c: c in "0123456789", "dec digit"):
                    pass

    return scoped_cursor.token("DEC")


def first_parser(parsers: list[Parser], cursor: Cursor) -> Token:
    for parser in parsers:
        try:
            return parser(cursor)
        except ParsingFailed:
            pass
    raise ParsingFailed()


def root_parser(cursor: Cursor) -> Generator[Token, None, None]:
    print(f"Root parser has {len(parser_registry.parsers)} parsers")
    while not isinstance(cursor.peek(), EOF):
        yield first_parser(parser_registry.parsers, cursor)


cursor = Cursor("1..2.2123")
for token in root_parser(cursor):
    print(token)
