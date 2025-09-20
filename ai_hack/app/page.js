import { Navigation } from "@/components/landingpage/Navigation";
import Image from "next/image";

export default function Home() {
  return (
    <div className="min-h-screen bg-background text-foreground overflow-hidden">
      {/* Animated Grid Background */}
      <div className="fixed inset-0 grid-pattern opacity-20 pointer-events-none" />

      <Navigation/>
      
    </div>
  );
}
