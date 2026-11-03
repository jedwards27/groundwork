"""General profile for any project that waits on outside organizations: a house renovation, a
store fit-out, a solar array. No ordering rules: it validates nothing it cannot know, and the
schedule's own dependencies are the only source of order."""

from groundwork.core.profile import DomainProfile

PROFILE = DomainProfile(
    name="general",
    role_class={
        "ahj": "regulator",
        "agency": "regulator",
        "regulator": "regulator",
        "to": "regulator",
        "iso": "regulator",
        "community": "regulator",
        "landlord": "counterparty_binding",
        "lender": "counterparty_binding",
        "investor": "counterparty_binding",
        "offtaker": "counterparty_binding",
        "contractor": "counterparty_routine",
        "designer": "counterparty_routine",
        "consultant": "counterparty_routine",
        "vendor": "counterparty_routine",
        "epc": "counterparty_routine",
        "developer": "counterparty_routine",
        "lessee": "counterparty_routine",
        "ie": "counterparty_routine",
        "operator": "counterparty_routine",
        "owner": "internal",
        "end_user": "internal",
    },
    # Assumptions: business days a party in this role takes to answer a routine request.
    response_lag_bd={"contractor": 3, "designer": 3, "consultant": 3, "vendor": 5, "landlord": 5},
    owner_extra_lag_bd={"ahj": 5, "agency": 5, "regulator": 10},
    reference_key=("item_code",),
    milestone_headline={
        "delivery": "{asset} is delivered in",
        "substantial_completion": "{asset} is substantially complete in",
        "final_acceptance": "{asset} is finished in",
        "energization": "{asset} is powered in",
        "cod": "{asset} starts operating in",
    },
    glossary={
        "critical path": "The chain of tasks that sets the finish date: a delay to any of them moves the date.",
        "slack": "How long a task can slip before it moves the finish date.",
        "AHJ": "Authority having jurisdiction: the local office that issues permits and inspections.",
    },
)
