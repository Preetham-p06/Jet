import { Navbar } from "@/components/landing/navbar";
import { Hero } from "@/components/landing/hero";
import { TrustStrip } from "@/components/landing/trust-strip";
import { Problem } from "@/components/landing/problem";
import { BeforeAfter } from "@/components/landing/before-after";
import { Features } from "@/components/landing/features";
import { TrueCost } from "@/components/landing/true-cost";
import { Intelligence } from "@/components/landing/intelligence";
import { Confidence } from "@/components/landing/confidence";
import { Workflow } from "@/components/landing/workflow";
import { ProposalDemo } from "@/components/landing/proposal-demo";
import { Roadmap } from "@/components/landing/roadmap";
import { AnalyticsDemo } from "@/components/landing/analytics-demo";
import { Integrations } from "@/components/landing/integrations";
import { Security } from "@/components/landing/security";
import { Pricing } from "@/components/landing/pricing";
import { Faq } from "@/components/landing/faq";
import { Cta } from "@/components/landing/cta";
import { Footer } from "@/components/landing/footer";

export default function Home() {
  return (
    <>
      <Navbar />
      <main id="main" className="relative z-10">
        <Hero />
        <TrustStrip />
        <Problem />
        <BeforeAfter />
        <Features />
        <TrueCost />
        <Intelligence />
        <Confidence />
        <Workflow />
        <ProposalDemo />
        <Roadmap />
        <AnalyticsDemo />
        <Integrations />
        <Security />
        <Pricing />
        <Faq />
        <Cta />
      </main>
      <Footer />
    </>
  );
}
