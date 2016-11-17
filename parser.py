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
        try:
            return (
                parser.specification.rules[self.rule].match(
                    parser,
                    *self.pattern_args
                )
            )
        except KeyError:
            raise NameError("rule {!r} unknown".format(self.rule))


class StringRule(RuleElement):
    def __init__(self, s: str) -> None:
        self.string = s  # type: str
        super().__init__()

    def match(self, parser: 'Parser') -> str:
        return parser.consume_string(self.string)


def _transmit_var(r: 'Rule', source: 'RuleElement') -> 'Rule':
    if source.var is None:
        return r
    else:
        copy = Rule(r.pattern_args, r.choices, r.actions)
        # type: 'Rule'
        copy.var = source.var
        return copy


class Rule(RuleElement):
    def __init__(self, pattern_args: List[Tuple[str, 'Rule']],
                 choices: List[List[RuleElement]],
                 actions: List[Optional[str]]) -> None:
        self.pattern_args = pattern_args  # type: List[Tuple[str, Rule]]
        self.choices = choices  # type: List[List[RuleElement]]
        self.actions = actions
        super().__init__()

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
                    _transmit_var(x[j.rule], j)
                    if (
                        isinstance(j, IncludedRule) and
                        j.rule in x.keys()
                    )
                    else j
                    for j in i
                ]
                for i in self.choices
            ], self.actions).match(parser)
        else:
            fails = []  # type: List[ParseFail]
            for i, action in zip(self.choices, self.actions):
                index = parser.index  # type: int
                try:
                    varspace = {}  # type: Dict[str, object]
                    last = None
                    for j in i:
                        if j.var is not None:
                            last = varspace[j.var] = j.match(parser)
                        else:
                            last = j.match(parser)
                    if action is None:
                        if len(i) != 1:
                            return parser.s[index:parser.index]
                        else:
                            return last
                    else:
                        namespace = parser.context.copy()
                        namespace.update(varspace)
                        return eval(action, namespace)
                except ParseFail as e:
                    fails.append(e)
                parser.index = index
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
        out = Rule(pattern_args, [], [])  # type: Rule
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
                    out.actions.append(None)
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
                            break
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
                elif source[index:index + 2] == "->":
                    action = ""
                    index2 = index + 2
                    while source[index2] != "{":
                        if not source[index2].isspace():
                            raise SyntaxError(
                                "A '->' should be followed by a '{'"
                            )
                        index2 += 1
                    opened = 1
                    index2 += 1
                    j = source[index2]
                    while opened > 0:
                        if j == "{":
                            opened += 1
                        elif j == "}":
                            opened -= 1
                        else:
                            if j in "'\"":
                                source += j
                                escaped = False
                                index3 = index2 + 1
                                while escaped or source[index3] != j:
                                    m = source[index3]
                                    action += m
                                    if not escaped and m == "\\":
                                        escaped = True
                                    elif escaped:
                                        escaped = False
                                    index3 += 1
                                index2 = index3
                        action += j
                        index2 += 1
                        if opened > 0 or index2 < len(source):
                            j = source[index2]
                    while j != "|" and index2 < len(source):
                        if not j.isspace():
                            raise SyntaxError(
                                "Nothing should follow an action"
                            )
                        index2 += 1
                        j = source[index2]
                    out.actions.append(
                        # compile(action[:-1], '<string>', 'eval')
                        action[:-1]  # for debug purposes
                    )
                    out.choices.append(current)
                    current = []
                    index = index2
                else:
                    name = i  # type: str
                    index2 = index + 1  # type: int
                    while index2 < len(source):
                        j = source[index2]  # type: str
                        if j.isspace() or j in "\"'<>|$-":
                            current.append(IncludedRule(name, []))
                            break
                        else:
                            name += j
                            index2 += 1
                    if index2 == len(source):
                        current.append(IncludedRule(name, []))
                    index = index2
            if current:
                out.choices.append(current)
                out.actions.append(None)
            if no_choice and len(out.choices) != 1:
                raise SyntaxError("choices are not allowed")
        except IndexError:
            raise SyntaxError("unexpected EOF")

        return out


Implementation = Optional[Callable[..., object]]


class ImplementationBoundRule(Rule):
    def __init__(self, name: str) -> None:
        super().__init__([], [], [])
        self.name = name  # type: str

    def match(self,
              parser: 'Parser', *args: Tuple['Rule', ...]) -> object:
        parser.context[self.name](parser, *args)


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
                rules[name] = ImplementationBoundRule(name)
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
        self.context = {}  # type: Dict[str, Callable[..., object]]

    def parse(self, s: str, p: str, closed: bool=True) -> object:
        self.s = s
        self.index = 0
        out = self.consume_pattern(p)  # type: object
        if closed and self.index != len(s):
            raise ParseFail(
                "Expected EOF, found {!r}".format(s[self.index:])
            )
        return out

    def consume_char(self) -> str:
        self.index += 1
        try:
            return self.s[self.index - 1]
        except IndexError:
            self.index -= 1
            raise ParseFail("Unexpected EOF")

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
