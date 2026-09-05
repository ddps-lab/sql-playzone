"""One public, versioned SQL comparison contract for authoring and judging."""

import re
from flask import abort


def parse_policy(data, current=None, creating=False):
    if "grading_policy" in data:
        policy = data["grading_policy"]
    elif "grading_order" in data or "grading_format" in data:
        try:
            order = []
            for item in filter(
                None,
                (part.strip() for part in data.get("grading_order", "").split(",")),
            ):
                match = re.fullmatch(r"([1-9][0-9]*)\s+(asc|desc)", item, re.IGNORECASE)
                if not match:
                    raise ValueError()
                order.append({"column": int(match[1]), "direction": match[2].lower()})
            formats = [
                int(item.strip())
                for item in data.get("grading_format", "").split(",")
                if item.strip()
            ]
            policy = dict(version=1, order_by=order, exact_format_columns=formats)
        except (ValueError, TypeError, AttributeError):
            abort(400, description="Invalid SQL grading columns")
    elif creating:
        policy = dict(version=1, order_by=[], exact_format_columns=[])
    else:
        return current
    if (
        not isinstance(policy, dict)
        or set(policy) != {"version", "order_by", "exact_format_columns"}
        or type(policy["version"]) is not int
        or policy["version"] != 1
    ):
        abort(400, description="Invalid SQL grading policy")
    order, formats = policy["order_by"], policy["exact_format_columns"]
    if (
        not isinstance(order, list)
        or not isinstance(formats, list)
        or len(order) > 64
        or len(formats) > 64
    ):
        abort(400, description="Invalid SQL grading columns")

    def column(value):
        return type(value) is int and 1 <= value <= 64

    if any(
        not isinstance(key, dict)
        or set(key) != {"column", "direction"}
        or not column(key["column"])
        or key["direction"] not in ("asc", "desc")
        for key in order
    ):
        abort(400, description="Invalid SQL grading order")
    if (
        any(not column(value) for value in formats)
        or len(set(formats)) != len(formats)
        or len({key["column"] for key in order}) != len(order)
    ):
        abort(400, description="Invalid or duplicate SQL grading column")
    return policy


def policy_notice(policy):
    if policy is None:
        return "출제자가 채점 기준을 확인 중입니다. 확인 전에는 채점하지 않으며 제출 횟수도 차감하지 않습니다."
    message = "MySQL 8.4 기준: 열 위치와 중복 행 수를 비교합니다. NULL은 문자열 NULL 및 빈 문자열과 구별합니다. 숫자는 정확한 값으로 비교하며 불필요한 끝자리 0은 무시합니다. 문자열의 대소문자·공백은 구별합니다."
    order = policy["order_by"]
    if order:
        message += (
            " 정렬: "
            + ", ".join(
                f"{key['column']}열 {'오름차순' if key['direction'] == 'asc' else '내림차순'}"
                for key in order
            )
            + ". 정렬 기준이 같은 행끼리는 순서가 자유롭습니다."
        )
    else:
        message += " 행 순서는 평가하지 않습니다."
    if policy["exact_format_columns"]:
        message += (
            " 표시 형식까지 일치해야 하는 열: "
            + ", ".join(map(str, policy["exact_format_columns"]))
            + ". 문제에 명시된 소수 자릿수 등 표시 형식을 지켜 주세요."
        )
    return message
