import { VerifyRecord } from "@/components/VerifyRecord";

export default function Page() {
  return <VerifyRecord site={process.env.GROUNDWORK_SITE ?? "lake-mariner"} />;
}
