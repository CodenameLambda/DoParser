#!/usr/bin/env python3

from typing import Optional, List, Tuple, Dict, Callable, TextIO, Union
from typing import cast
import re
import os.path
import importlib.machinery

import stdlib as stdlib_implementation


class ParseFail(Exception):
    pass


class TriggeredParseFail(ParseFail):
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


class Rule(RuleElement):
    def __init__(self, pattern_args: List[Tuple[str, Optional['Rule']]],
                 choices: List[List[RuleElement]],
                 actions: List[Optional[str]]) -> None:
        self.choices = choices  # type: List[List[RuleElement]]
        self.actions = actions  # type: List[Optional[str]]
        self.pattern_args = pattern_args
        # type: List[Tuple[str, Optional[Rule]]]
        super().__init__()

    def match(self, parser: 'Parser', *args: 'Rule',
              augmented_namespace: Optional[Dict[str, 'Rule']]=None
              ) -> object:
        if augmented_namespace is None:
            augmented_namespace = {  # type: Dict[str, Rule]
                name: default
                for name, default in self.pattern_args
                if default is not None
            }
            augmented_namespace.update({
                nd[0]: v
                for nd, v in zip(self.pattern_args, args)
            })

        fails = []  # type: List[ParseFail]
        for i, action in zip(self.choices, self.actions):
            index = parser.index  # type: int
            try:
                varspace = {}  # type: Dict[str, object]
                last = None
                for j in i:
                    var = j.var
                    if isinstance(j, IncludedRule):
                        pattern_args = []  # type: List[Rule]
                        if j.rule in augmented_namespace.keys():
                            j = augmented_namespace[j.rule]
                        else:
                            pattern_args = j.pattern_args
                            j = parser.specification.rules[j.rule]
                        last = (
                            j.match(
                                parser,
                                *pattern_args,
                                augmented_namespace=(
                                    augmented_namespace
                                    if augmented_namespace
                                    else None
                                )
                            )
                        )
                    else:
                        last = j.match(parser)
                    if var is not None:
                        varspace[var] = last
                if action is None:
                    if len(i) != 1:
                        return parser.s[index:parser.index]
                    else:
                        return last
                else:
                    namespace = parser.context.copy()
                    # type: Dict[str, object]
                    namespace.update(varspace)
                    return eval(action, namespace)
            except ParseFail as e:
                if isinstance(e, TriggeredParseFail):
                    raise ParseFail(*e.args)
                else:
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
    def parse(pattern_args: List[Tuple[str, 'Rule']],
              source: str) -> 'Rule':
        out = Rule(pattern_args, [], [])  # type: Rule
        if source.strip() == "":
            raise SyntaxError("rule source can't be empty.\n"
                              "Tip: Use '\"\"' instead.")
        try:
            c = ""  # type: str
            index2 = 0  # type: int
            j = "\0"  # type: str
            opened = 0  # type: int
            current = []  # type: List[RuleElement]
            index = 0  # type: int
            while index < len(source):
                i = source[index]  # type: str
                if i in "\"'":
                    c = ""
                    index2 = index + 1
                    while True:
                        j = source[index2]
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
                    c = ""
                    index2 = index + 1
                    while index2 < len(source):
                        j = source[index2]
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
                    ps = []  # type: List[str]
                    c = ""
                    index2 = index + 1
                    opened = 1
                    while True:
                        j = source[index2]
                        if j == ">":
                            opened -= 1
                            if opened == 0:
                                if c == "":
                                    raise SyntaxError("too many commas")
                                if isinstance(current[-1],
                                              IncludedRule):
                                    current[-1].pattern_args += [
                                        Rule.parse([], m)
                                        for m in ps + [c]
                                    ]
                                else:
                                    raise SyntaxError(
                                        "a string can't have template "
                                        "arguments"
                                    )
                                break
                            else:
                                c += ">"
                                index2 += 1
                        elif j == "<":
                            c += j
                            index2 += 1
                            opened += 1
                        elif j == "," and opened == 1:
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
                    action = ""  # type: str
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
                                action += j
                                escaped = False  # type: bool
                                index3 = index2 + 1  # type: int
                                while escaped or source[index3] != j:
                                    m = source[index3]  # type: str
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
                        action[:-1]  # DEBUG
                    )
                    out.choices.append(current)
                    current = []
                    index = index2
                else:
                    name = i  # type: str
                    index2 = index + 1
                    while index2 < len(source):
                        j = source[index2]
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
        except IndexError:
            raise SyntaxError("unexpected EOF")

        return out

    @property
    def pattern_args(self) -> List[Tuple[str, 'Rule']]:
        assert self._pattern_args is not None
        return self._pattern_args

    @pattern_args.setter
    def pattern_args(self, value: List[Tuple[str, 'Rule']]) -> None:
        self._pattern_args = value
        for i in self.choices:
            for j in i:
                if isinstance(j, IncludedRule):
                    for m in j.pattern_args:
                        assert isinstance(m, Rule)
                        m.pattern_args = value


class ImplementationBoundRule(Rule):
    def __init__(self, name: str) -> None:
        super().__init__([], [], [])
        self.name = name  # type: str

    def match(self, parser: 'Parser', *args: 'Rule', **_) -> object:
        implementation = parser.context[self.name]  # type: object
        if isinstance(implementation, cast(type, Callable)):
            return cast(Callable[..., object], implementation)(
                parser,
                *args
            )


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
        def parse_line(line):
            if not _rule_re.match(line):
                raise SyntaxError("formal error")
            pattern_args = []  # type: List[Tuple[str, Rule]]
            current_parg = [""]  # type: List[Optional[str]]
            mode = "name"  # type: str
            name = ""  # type: str
            implementation = ""  # type: str
            for j in line:
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
            if implementation.lstrip() == "...":
                rules[name] = ImplementationBoundRule(name)
            else:
                rules[name] = Rule.parse(
                    pattern_args,
                    implementation
                )

        rules = {}  # type: Dict[str, Rule]
        current = ""
        for i in (i.rstrip() for i in source.split("\n")):
            if i == "":
                pass
            elif i[0].isspace():
                current += i
            elif current != "":
                parse_line(current)
                current = i
            else:
                current = i
        if current != "":
            parse_line(current)
        return Specification(rules)


class Parser(object):
    def __init__(self, specification: Specification) -> None:
        self.specification = specification  # type: Specification
        self.s = None  # type: Optional[str]
        self.index = None  # type: Optional[int]
        self.context = {}  # type: Dict[str, object]

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

    def consume_eof(self) -> None:
        if len(self.s) != self.index:
            raise ParseFail(
                "Expected EOF, found {!r}".format(self.s[self.index:])
            )

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
                        *args: Rule) -> object:
        return self.specification.rules[pattern].match(self, *args)

    def _lookahead(self, pattern: str) -> object:
        jump_back = self.index  # type: int
        x = self.consume_pattern(pattern)
        self.index = jump_back
        return x


stdlib_specification = None  # type: Optional[Specification]


def init() -> None:
    global stdlib_specification

    f = cast(TextIO, open("stdlib.dparse", "r"))  # type: TextIO
    stdlib_specification = Specification.parse(f.read())
    f.close()


class File(object):
    def __init__(self, path: str,
                 context: Optional[Dict[str, object]]=None) -> None:
        if stdlib_specification is None:
            init()
        out = stdlib_specification.rules.copy()  # type: Dict[str, Rule]
        todo = [path]  # type: List[str]
        if context is None:
            context = {}
        else:
            context = context.copy()
        for i in dir(stdlib_implementation):
            if not i.startswith("_") and i not in context.keys():
                context[i] = getattr(
                    stdlib_implementation,
                    i
                )
        while todo:
            new_todo = []  # type: List[str]
            for i in todo:
                f = cast(TextIO, open(i, "r"))  # type: TextIO
                source = ""  # type: str
                for j in f.readlines():
                    if j.startswith("include "):
                        x = path.rsplit("/", 2)  # type: List[str]
                        if len(x) == 1:
                            x = ["."]
                        new_todo.append(
                            os.path.join(
                                x[0],
                                j[len("include "):].strip()
                            )
                        )
                    elif j.startswith("#"):
                        pass
                    else:
                        source += j + "\n"
                out.update(Specification.parse(source).rules)
                pyfile = i.rsplit(".", 2)[0] + ".py"  # type: str
                if os.path.exists(pyfile):
                    module = importlib.machinery.SourceFileLoader(
                        i.rsplit(".", 2)[0],
                        pyfile
                    )
                    for i in dir(module):
                        if not i.startswith("_"):
                            context[i] = getattr(
                                stdlib_implementation,
                                i
                            )
            todo = new_todo
        self.parser = Parser(Specification(out))
        self.parser.context = context

    def parse(self, s, closed: bool=True):
        return self.parser.parse(s, "main", closed)
