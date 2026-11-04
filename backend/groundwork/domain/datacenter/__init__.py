"""Data-center build profile.

Every rule below that is marked ``assumption=True`` is an assumption about how utilities,
inspectors or commissioning teams behave, and must be checked with a practitioner.
"""

from groundwork.core.profile import DomainProfile, OrderRule

PROFILE = DomainProfile(
    name="datacenter",
    order_rules=(
        OrderRule(
            "protection_coordination_study",
            "protection_settings_submittal",
            "relay trip settings are derived from the coordination study",
        ),
        OrderRule(
            "protection_settings_submittal",
            "to_settings_acceptance",
            "the transmission owner (TO) accepts what was submitted",
        ),
        OrderRule(
            "to_settings_acceptance",
            "to_witness_test",
            "the TO will not witness protection tests on settings it has not accepted",
        ),
        OrderRule(
            "electrical_cut_in_certificate",
            "to_witness_test",
            "NY utilities commonly require the inspection agency's cut-in certificate before "
            "energizing customer gear (practitioner question 19)",
            assumption=True,
        ),
        OrderRule("switchgear_delivery", "to_witness_test", "the witnessed gear must be on site"),
        OrderRule(
            "to_witness_test",
            "cx_l3",
            "L3 start-up runs on permanent utility power; some sites start up on generators "
            "first (practitioner question 20)",
            assumption=True,
        ),
        OrderRule("cx_l2", "cx_l3", "commissioning levels are strictly sequential"),
        OrderRule("cx_l3", "cx_l4", "commissioning levels are strictly sequential"),
        OrderRule("cx_l4", "cx_l5", "commissioning levels are strictly sequential"),
        OrderRule(
            "electrical_cut_in_certificate",
            "temporary_certificate_of_occupancy",
            "Niagara County towns issue a CO only after the agency's final electrical certificate",
            assumption=True,
        ),
        OrderRule(
            "generator_air_permit",
            "generator_delivery",
            "a DEC permit to construct, where required, precedes generator installation "
            "(practitioner question 4, Executive Order 62)",
            assumption=True,
        ),
    ),
    role_class={
        "to": "regulator",
        "iso": "regulator",
        "ahj": "regulator",
        "agency": "regulator",
        "regulator": "regulator",
        "community": "regulator",
        "landlord": "counterparty_binding",
        "lender": "counterparty_binding",
        "investor": "counterparty_binding",
        "offtaker": "counterparty_binding",
        # The principal's own independent engineer is a contractor it engages directly. A lender's
        # independent engineer is modeled with role "lender" and is record-bearing.
        "ie": "counterparty_routine",
        "lessee": "counterparty_routine",
        "developer": "counterparty_routine",
        "vendor": "counterparty_routine",
        "epc": "counterparty_routine",
        "operator": "counterparty_routine",
        "end_user": "internal",
        "owner": "internal",
        "contractor": "counterparty_routine",
        "designer": "counterparty_routine",
        "consultant": "counterparty_routine",
    },
    # Assumptions to verify (practitioner question 18): business days to get a response.
    response_lag_bd={"lessee": 5, "landlord": 5, "developer": 5, "epc": 5, "vendor": 5, "ie": 3},
    owner_extra_lag_bd={"to": 10, "iso": 10, "ahj": 5, "agency": 5, "regulator": 10},
    reference_key=("iso_region", "item_code"),
    milestone_headline={
        "delivery": "{asset} delivers in",
        "energization": "{asset} energizes in",
        "cod": "{asset} reaches commercial operation in",
        "substantial_completion": "{asset} reaches substantial completion in",
        "final_acceptance": "{asset} final acceptance in",
    },
    glossary={
        "TO": "Transmission owner: the utility that owns the high-voltage lines and substation the site connects to.",
        "ISO": "Independent system operator: runs the regional grid and its queue of connection requests (NYISO here).",
        "AHJ": "Authority having jurisdiction: the local office that issues permits and certificates of occupancy.",
        "POI": "Point of interconnection: where the customer's equipment meets the TO's.",
        "coordination study": "Engineering study that sets protective-relay trip settings so faults clear in the right order.",
        "short-circuit data": "The TO's figures for available fault current at the POI; an input to the coordination study.",
        "witness test": "The TO watching the customer's protection and switching tests before allowing energization.",
        "cut-in certificate": "The electrical inspection agency's sign-off a utility often requires before energizing customer gear.",
        "L2–L5": "Commissioning levels: installation checks, start-up, functional performance test, integrated systems test.",
        "L4": "Functional performance test; the contractual delivery milestone in the Lake Mariner leases (per TeraWulf's Q2 2026 call).",
        "FAT": "Factory acceptance test of equipment before it ships.",
        "hipot": "High-potential test: a high-voltage insulation test.",
        "LD": "Liquidated damages: a contractually fixed payment for lateness.",
        "TCO": "Temporary certificate of occupancy for a hall.",
        "IE": "Independent engineer: a technical reviewer who witnesses tests on the owner's behalf. A lender's IE is a different party, modeled with the lender role.",
        "HLF": "NYPA's high-load-factor economic-development power program: an allocation of market power, not grid capacity.",
        "EO 62": "New York Executive Order 62 (July 2026): holds DEC permits for data centers of 50 MW or more in abeyance unless the application was complete before the order.",
    },
)
