import os
from decimal import Decimal
import json
import datetime
from rich.console import Console
from brownie import Contract, Wei
from ape_safe import ApeSafe
from scripts.systems.addresses import ADDRESSES_ETH, checksum_address_dict
from scripts.dev_multisig.emissions.helper_printout import print_logger_unlock_schedules
from scripts.dev_multisig.emissions.dynamic_tvl_emissions import dynamic_bveCVX_emissions

console = Console()

# addresses involved
ADDRESSES = checksum_address_dict(ADDRESSES_ETH)
treasury_tokens = ADDRESSES["treasury_tokens"]
sett_vaults = ADDRESSES["sett_vaults"]
REWARDS_LOGGER = "0x0A4F4e92C3334821EbB523324D09E321a6B0d8ec"

# 7 days
DURATION = 604800

AUTOCOMPOUND_50_SETTS = [
    sett_vaults["bBADGER"],
    sett_vaults["buniWbtcBadger"],
    sett_vaults["bslpWbtcBadger"],
    sett_vaults["bslpWbtcDigg"],
]

AUTOCOMPOUND_100_SETTS = [
    sett_vaults["bDIGG"],
]


def main():
    path = os.getcwd() + "/scripts/dev_multisig/emissions/emissions_info.json"
    with open(path) as f:
        # for testing currently, ideally to be grab from a source of truth (TODO!)
        data = json.load(f)

    weekly_emissions(data)


def weekly_emissions(data, submitTx=True):
    today = datetime.date.today()
    target_week = find_thrusday(today)

    emissions_data = data[target_week.strftime("%d-%m-%y")]
    time_range = emissions_data["timerange"]

    safe = ApeSafe("0x86cbD0ce0c087b482782c181dA8d191De18C8275")
    Contract.from_explorer(treasury_tokens["DIGG"])
    digg = safe.contract(treasury_tokens["DIGG"])

    try:
        rewards_logger = safe.contract(REWARDS_LOGGER)
    except:
        Contract.from_explorer(REWARDS_LOGGER)
        rewards_logger = safe.contract(REWARDS_LOGGER)

    totals = {"badger": 0, "digg": 0}

    for sett in emissions_data["setts"]:
        beneficiary = sett["address"]

        if sett["badger_allocation"] != 0:
            #  make difference between native setts as per WeeklyEmissions.md
            if beneficiary in AUTOCOMPOUND_50_SETTS:
                formatted_amount = Wei(f'{sett["badger_allocation"]} ether') // 2
            elif beneficiary in AUTOCOMPOUND_100_SETTS:
                continue  # nothing to emit
            else:
                formatted_amount = Wei(f'{sett["badger_allocation"]} ether')

            totals["badger"] += formatted_amount

            rewards_logger.setUnlockSchedule(
                beneficiary,
                treasury_tokens["BADGER"],
                formatted_amount,
                time_range["starttime"],
                time_range["endtime"],
                DURATION,
            )
        if sett["digg_allocation"] != 0:
            if beneficiary in AUTOCOMPOUND_50_SETTS:
                initial_fragments = sett["digg_allocation"] * 10 ** digg.decimals()
                shares = Decimal((initial_fragments * digg._initialSharesPerFragment()) // 2)
            elif beneficiary in AUTOCOMPOUND_100_SETTS:
                continue

            totals["digg"] += shares

            rewards_logger.setUnlockSchedule(
                beneficiary,
                treasury_tokens["DIGG"],
                shares,
                time_range["starttime"],
                time_range["endtime"],
                DURATION,
            )

    safe_tx = safe.multisend_from_receipts()

    # console output
    print(
        f"Total emissions during {target_week.strftime('%d-%m-%y')} : badger={totals['badger']} and digg={totals['digg']}"
    )

    print("\n")

    print_logger_unlock_schedules(rewards_logger, digg)

    console.print("\npreview()\n")
    safe.preview(safe_tx, call_trace=True)

    if submitTx:
        safe_tx.safe_tx_gas = 4000000
        safe.post_transaction(safe_tx)


def find_thrusday(date):
    THRUSDAY = 4
    year, week, day = date.isocalendar()
    delta = datetime.timedelta(days=THRUSDAY - day)
    return date + delta
