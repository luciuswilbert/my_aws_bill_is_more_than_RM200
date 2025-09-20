import { Button } from "@/components/ui/button"
import { Sparkles } from "lucide-react"

export function Navigation() {
  return (
    <nav className="relative z-50 flex items-center justify-between p-6 lg:px-8">
      <div className="flex items-center gap-2">
        <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center animate-pulse-glow">
          <Sparkles className="w-5 h-5 text-primary-foreground" />
        </div>
        <span className="text-xl font-bold text-balance">JustMarketing</span>
      </div>
      <div className="hidden md:flex items-center gap-8">
        <a href="#features" className="text-muted-foreground hover:text-foreground transition-colors">
          Features
        </a>
        <a href="#testimonials" className="text-muted-foreground hover:text-foreground transition-colors">
          Reviews
        </a>
        <a href="#pricing" className="text-muted-foreground hover:text-foreground transition-colors">
          Pricing
        </a>
      </div>
      <Button variant="outline" className="border-primary/20 hover:bg-primary/10 bg-transparent">
        Sign In
      </Button>
    </nav>
  )
}
