#!/usr/bin/env python3

from typing import Optional, List, Tuple, Dict, Callable
import re


class ParseFail(Exception):
    pass


class RuleElement(object):
    def __init__(self, var: Optional[str] = None) -> None:
        self.var = var  # type: Optional[str]

    def match(self, parser: 'Parser') -> object:
        raise NotImplemented()


class IncludedRule(RuleElement):
    def __init__(self, rule: str, pattern_args: List['Rule']) -> None:
        self.rule = rule  # type: str
        self.pattern_args = pattern_args  # type: List['Rule']
        super().__init__()

    def match(self, parser: 'Parser') -> object:
        return (
            parser.specification.rules[self.rule].match(
                parser,
                *self.pattern_args
            )
        )


class StringRule(RuleElement):
    def __init__(self, s: str) -> None:
        self.string = s  # type: str
        super().__init__()

    def match(self, parser: 'Parser') -> str:
        return parser.consume_string(self.string)


class Rule(object):
    def __init__(self, pattern_args: List[Tuple[str, 'Rule']],
                 choices: List[List[RuleElement]]) -> None:
        self.pattern_args = pattern_args  # type: List[Tuple[str, Rule]]
        self.choices = choices  # type: List[List[RuleElement]]

    def match(self, parser: 'Parser',
              *args: Tuple['Rule', ...]) -> object:
        if len(args) != len(self.pattern_args):
            raise TypeError()

        if args:
            x = {  # type: Dict[str, Rule]
                   name: default
                   for name, default in self.pattern_args
                   if default is not None
                   }
            x.update({
                         nd[0]: v
                         for nd, v in zip(self.pattern_args, args)
                         })
            return Rule([], [
                [
                    args[x[j]] if j in x.keys() else j
                    for j in i
                    ]
                for i in self.choices
                ]).match(parser)
        else:
            fails = []  # type: List[ParseFail]
            for i in self.choices:
                index = parser.index  # type: int
                try:
                    varspace = {}  # type: Dict[str, object]
                    for j in i:
                        if j.var is not None:
                            varspace[j.var] = j.match(parser)
                        else:
                            j.match(parser)
                    # TODO: Actions
                    return parser.s[index:parser.index]
                except ParseFail as e:
                    fails.append(e)
            if len(fails) == 1:
                raise fails[0]
            else:
                raise ParseFail(
                    "All alternatives failed:\n    {}".format(
                        "\n    ".join(
                            i.args[0]
                            if len(i.args) != 0
                            else "(unknown)"
                            for i in fails
                        )
                    )
                )

    @staticmethod
    def parse(pattern_args: List[Tuple[str, 'Rule']], source: str, *,
              no_choice: bool = False) -> 'Rule':
        if source.strip() == "...":
            return ImplementationBoundRule()
        out = Rule(pattern_args, [])  # type: Rule
        if source.strip() == "":
            raise SyntaxError("rule source can't be empty.\n"
                              "Tip: Use '\"\"' instead.")
        try:
            current = []  # type: List[RuleElement]
            index = 0  # type: int
            while index < len(source):
                i = source[index]  # type: str
                if i in "\"'":
                    c = ""  # type: str
                    index2 = index + 1  # type: int
                    while True:
                        j = source[index2]  # type: str
                        if j == i:
                            current.append(StringRule(c))
                            break
                        elif j == "\\":
                            if source[index2 + 1] == "x":
                                c += chr(
                                    int(source[index2 + 2:index2 + 4])
                                )
                            elif source[index2 + 1] == "n":
                                c += "\n"
                            elif source[index2 + 1] == "t":
                                c += "\t"
                            elif source[index2 + 1] == "\\":
                                c += "\\"
                            elif source[index2 + 1] in "\"'":
                                c += source[index2 + 1]
                            else:
                                raise SyntaxError(
                                    "unknown escape sequence"
                                )
                            index2 += 2
                        else:
                            c += j
                            index2 += 1
                    index = index2 + 1
                elif i == "|":
                    out.choices.append(current)
                    current = []
                    index += 1
                elif i == "$":
                    c = ""  # type: str
                    index2 = index + 1  # type: int
                    while index2 < len(source):
                        j = source[index2]  # type: str
                        if not (j.isalpha() or j.isdigit()):
                            if c == "":
                                raise SyntaxError("empty identifier")
                            current[-1].var = c
                        else:
                            c += j
                            index2 += 1
                    index = index2
                elif i == "<":
                    ps = []  # List[str]
                    c = ""  # type: str
                    index2 = index + 1  # type: int
                    while True:
                        j = source[index2]  # type: str
                        if j == ">":
                            if c == "":
                                raise SyntaxError("too many commas")
                            if isinstance(current[-1], IncludedRule):
                                current[-1].pattern_args += [
                                    Rule.parse([], m, no_choice=True)
                                    for m in ps + [c]
                                    ]
                            else:
                                raise SyntaxError(
                                    "a string can't have template "
                                    "arguments"
                                )
                            break
                        elif j == ",":
                            if c == "":
                                raise SyntaxError("too many commas")
                            ps.append(c)
                            c = ""
                            index2 += 1
                        else:
                            c += j
                            index2 += 1
                    index = index2 + 1
                elif i.isspace():
                    index += 1
                else:
                    name = i  # type: str
                    index2 = index + 1  # type: int
                    while index2 < len(source):
                        j = source[index2]  # type: str
                        if j.isspace() or j in "\"'<>|":
                            current.append(IncludedRule(name, []))
                            break
                        else:
                            name += j
                            index2 += 1
                    if index2 == len(source):
                        current.append(IncludedRule(name, []))
                    index = index2
                    # TODO: Parse actions
            out.choices.append(current)
            if no_choice and len(out.choices) != 1:
                raise SyntaxError("choices are not allowed")
        except IndexError:
            raise SyntaxError("unexpected end")

        return out


Implementation = Optional[Callable[..., object]]


class ImplementationBoundRule(Rule):
    def __init__(self, implementation: Implementation=None) -> None:
        super().__init__([], [])
        self.implementation = implementation  # type: Implementation

    def match(self,
              parser: 'Parser', *args: Tuple['Rule', ...]) -> object:
        self.implementation(parser, *args)


_rule_re = re.compile(
    r"^"
    r"([^<>=, ]+) *"
    r"(< *([^<>=, ]+( *= *([^<>=, ]+))?) *"
    r"(, *([^<>=, ]+( *= *[^<>=, ]+)?))* *>)? "
    r" *= *(.+)$"
)


class Specification(object):
    def __init__(self, rules: Dict[str, Rule]) -> None:
        self.rules = rules  # type: Dict[str, Rule]

    @staticmethod
    def parse(source: str) -> 'Specification':
        rules = {}  # type: Dict[str, Rule]
        for i in (i.strip() for i in source.split("\n")):
            if i == "":
                continue
            if not _rule_re.match(i):
                raise SyntaxError("formal error")
            pattern_args = []  # type: List[Tuple[str, Rule]]
            current_parg = [""]  # type: List[Optional[str]]
            mode = "name"  # type: str
            name = ""  # type: str
            implementation = ""  # type: str
            for j in i:
                if mode == "name":
                    if j == "<":
                        mode = "pattern_args"
                    elif j == "=":
                        mode = "implementation"
                    elif not j.isspace():
                        name += j
                elif mode == "pattern_args":
                    if j == ">":
                        mode = "preimplementation"
                    elif j == "=":
                        current_parg.append("")
                    elif j == ",":
                        if len(current_parg) < 2:
                            current_parg.append(None)
                        pattern_args.append(tuple(current_parg))
                        current_parg = [""]
                    elif not j.isspace():
                        current_parg[-1] += j
                elif mode == "preimplementation":
                    if j == "=":
                        if len(current_parg) < 2:
                            current_parg.append(None)
                        pattern_args.append(tuple(current_parg))
                        mode = "implementation"
                else:
                    implementation += j
            if implementation == "...":
                rules[name] = ImplementationBoundRule()
            else:
                rules[name] = Rule.parse(
                    pattern_args,
                    implementation
                )
        return Specification(rules)


class Parser(object):
    def __init__(self, specification: Specification) -> None:
        self.specification = specification  # type: Specification
        self.s = None  # type: Optional[str]
        self.index = None  # type: Optional[int]

    def parse(self, s: str, p: str) -> object:
        self.s = s
        self.index = 0
        return self.consume_pattern(p)

    def consume_char(self) -> str:
        self.index += 1
        return self.s[self.index - 1]

    def consume_string(self, s: str) -> str:
        l = len(s)  # type: int
        self.index += l
        if self.s[self.index - l:self.index] != s:
            raise ParseFail(
                "Expected {!r}, saw {!r}".format(
                    s,
                    self.s[self.index - l:self.index]
                )
            )
        else:
            return s

    def consume_pattern(self, pattern: str,
                        *args: Tuple[Rule, ...]) -> object:
        return self.specification.rules[pattern].match(self, *args)

    def _lookahead(self, pattern: str) -> object:
        jump_back = self.index  # type: int
        x = self.consume_pattern(pattern)
        self.index = jump_back
        return x
