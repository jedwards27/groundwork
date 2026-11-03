// The stage tracker groups the chain's items into the phases a reader expects. This mapping is
// data-center specific (the web app is the data-center vertical's UI); items with unknown codes
// fall back to their kind.
import type { ItemView } from "./types";

const STAGES: { key: string; label: string; codes: string[] }[] = [
  { key: "interconnection", label: "Interconnection", codes: ["protection_coordination_study", "protection_settings_submittal", "to_settings_acceptance", "revenue_metering", "to_witness_test"] },
  { key: "permits", label: "Permits", codes: ["building_permit", "generator_air_permit", "site_plan_condition"] },
  { key: "equipment", label: "Long-lead equipment", codes: ["power_transformer_delivery", "switchgear_delivery", "generator_delivery", "ups_battery_delivery", "cooling_equipment_delivery"] },
  { key: "install", label: "Installation", codes: ["electrical_install_complete", "mechanical_install_complete", "cx_l2"] },
  { key: "certificates", label: "Certificates", codes: ["electrical_cut_in_certificate", "temporary_certificate_of_occupancy"] },
  { key: "commissioning", label: "Commissioning", codes: ["cx_l3", "cx_l4"] },
  { key: "delivered", label: "Delivered", codes: ["lease_delivery_milestone"] },
];

export interface StageState {
  key: string;
  label: string;
  status: "done" | "active" | "delayed" | "pending";
  note: string;
}

// Only the stages this project has items for: none, for a project outside the data-center vertical.
export function stages(items: ItemView[]): StageState[] {
  return STAGES.filter((s) => items.some((i) => s.codes.includes(i.code))).map((s) => {
    const its = items.filter((i) => s.codes.includes(i.code));
    const done = its.length > 0 && its.every((i) => i.status === "done");
    const late = its.filter((i) => i.status !== "done" && i.finish_shift_days > 0);
    const active = its.some((i) => i.status === "in_progress");
    const status = done ? "done" : late.length ? "delayed" : active ? "active" : "pending";
    const note = done
      ? "done"
      : late.length
        ? `+${Math.max(...late.map((i) => i.finish_shift_days))} d`
        : active
          ? "in progress"
          : "pending";
    return { key: s.key, label: s.label, status, note };
  });
}
