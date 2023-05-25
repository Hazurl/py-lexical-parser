from contextlib import contextmanager
from dataclasses import dataclass
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


class Cursor:
    def __init__(self, text: str, index: int = 0) -> None:
        self.text = text
        self.index = index

    def peek(self) -> str | EOF:
        return self.text[self.index] if self.index < len(self.text) else EOF()

    def eat_if(self, predicate: Callable[[str], bool], comment: str) -> str:
        chr = self.peek()
        if not isinstance(chr, EOF) and predicate(chr):
            # print(f"Eat: At index {self.index} '{chr}' while parsing {comment}")
            self.index += 1
            return chr

        # print(f"Raise EatFailed: At index {self.index} '{chr}' while parsing {comment}")
        raise EatFailed(f"At index {self.index} '{chr}' while parsing {comment}", failed_on_eof=isinstance(chr, EOF))


class CursorWrapper:
    def __init__(self, cursor: Cursor):
        self.cursor = cursor
        self.enter_index = self.cursor.index

    def peek(self) -> str | EOF:
        return self.cursor.peek()

    def eat_if(self, predicate: Callable[[str], bool], comment: str) -> str:
        return self.cursor.eat_if(predicate, comment)

    def reset(self) -> None:
        self.cursor.index = self.enter_index

    def token(self, ty: str) -> Token:
        value = self.cursor.text[self.enter_index : self.cursor.index - self.enter_index]
        return Token(ty, value, self.enter_index, self.cursor.index - 1)

    def eat(self) -> str:
        return self.eat_if(lambda _: True, "any char")

    def eat_only(self, chr: str) -> str:
        return self.eat_if(lambda c: c == chr, f"only '{chr}'")

    def eat_any(self, lchr: str) -> str:
        return self.eat_if(lambda c: c in lchr, f"any of '{lchr}'")


@contextmanager
def scoped(cursor: Cursor) -> Generator[CursorWrapper, None, None]:
    wrapper = CursorWrapper(cursor)
    try:
        yield wrapper
    except EatFailed:
        wrapper.reset()
        raise ParsingFailed()


@contextmanager
def guard(eof_only: bool = False) -> Generator[None, None, None]:
    try:
        yield
    except EatFailed as e:
        if e.failed_on_eof or not eof_only:
            pass
        else:
            raise


def p_str(cursor: Cursor) -> Token:
    with scoped(cursor) as scoped_cursor:
        quote = scoped_cursor.eat_any("'\"")
        with guard():
            while scoped_cursor.eat_if(lambda c: c != quote, f"anything but {quote}"):
                pass
        scoped_cursor.eat_only(quote)

    return scoped_cursor.token("STRING")


def p_dot(cursor: Cursor) -> Token:
    with scoped(cursor) as scoped_cursor:
        scoped_cursor.eat_only(".")

    return scoped_cursor.token("DOT")


def p_hex(cursor: Cursor) -> Token:
    with scoped(cursor) as scoped_cursor:
        scoped_cursor.eat_only("0")
        scoped_cursor.eat_only("x")
        scoped_cursor.eat_if(lambda c: c in "0123456789abcdefABCDEF", "hex digit")

        with guard():
            while scoped_cursor.eat_if(lambda c: c in "0123456789abcdefABCDEF", "hex digit"):
                pass

    return scoped_cursor.token("HEX")


Parser = Callable[[Cursor], Token]


def first_parser(parsers: list[Parser], cursor: Cursor) -> Token:
    for parser in parsers:
        try:
            return parser(cursor)
        except ParsingFailed:
            pass
    raise ParsingFailed()


def root_parser(cursor: Cursor) -> Generator[Token, None, None]:
    while not isinstance(cursor.peek(), EOF):
        yield first_parser([p_str, p_hex, p_dot], cursor)


cursor = Cursor("0x123abc.'abc'.")
for token in root_parser(cursor):
    print(token)
