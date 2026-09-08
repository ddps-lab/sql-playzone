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
        return (
            "The challenge author is reviewing the grading requirements. "
            "Grading is unavailable until the review is complete. No attempts will be deducted."
        )
    message = (
        "Grading uses MySQL 8.4. Column positions and duplicate row counts must match. "
        "NULL differs from the string 'NULL' and an empty string. "
        "Numbers are compared by exact value, ignoring unnecessary trailing zeros. "
        "String comparisons are case-sensitive and preserve whitespace."
    )
    order = policy["order_by"]
    if order:
        message += (
            " Sort order: "
            + ", ".join(
                f"column {key['column']} {'ascending' if key['direction'] == 'asc' else 'descending'}"
                for key in order
            )
            + ". Rows with equal sort keys may appear in any order."
        )
    else:
        message += " Row order is not graded."
    if policy["exact_format_columns"]:
        message += (
            " Columns requiring exact formatting: "
            + ", ".join(map(str, policy["exact_format_columns"]))
            + ". Follow the formatting requirements in the challenge description, such as decimal places."
        )
    return message
