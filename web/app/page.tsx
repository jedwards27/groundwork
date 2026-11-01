import { MissionControl } from "@/components/MissionControl";

export default function Page() {
  return <MissionControl site={process.env.GROUNDWORK_SITE ?? "lake-mariner"} />;
}
