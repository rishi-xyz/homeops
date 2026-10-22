import Link from "next/link";

export default function LandingPage() {
  return (
    <div className="min-h-screen">
      {/* Navigation */}
      <nav className="fixed top-0 w-full z-50 glass">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center font-bold text-lg">
              HO
            </div>
            <span className="text-xl font-bold font-[family-name:var(--font-space-grotesk)]">HomeOps</span>
          </div>
          <div className="hidden md:flex items-center gap-8">
            <a href="#features" className="text-gray-300 hover:text-white transition-colors">Features</a>
            <a href="#how-it-works" className="text-gray-300 hover:text-white transition-colors">How it Works</a>
            <a href="#tech" className="text-gray-300 hover:text-white transition-colors">Tech Stack</a>
          </div>
          <Link href="/demo" className="btn-primary px-6 py-2.5 rounded-xl font-medium">
            Try Demo
          </Link>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="pt-32 pb-20 px-6">
        <div className="max-w-7xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full glass mb-8">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span className="text-sm text-gray-300">Powered by MCP • Amazon Bedrock • Real-time Intelligence</span>
          </div>
          
          <h1 className="text-5xl md:text-7xl font-bold font-[family-name:var(--font-space-grotesk)] mb-6 leading-tight">
            Your Home's
            <span className="gradient-text"> AI Command Center</span>
          </h1>
          
          <p className="text-xl md:text-2xl text-gray-400 max-w-3xl mx-auto mb-10 leading-relaxed">
            Track appliances, warranties, maintenance history, and get AI-powered technician briefs. 
            Never miss a warranty expiry or forget a repair again.
          </p>
          
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-16">
            <Link href="/demo" className="btn-primary px-8 py-4 rounded-xl font-semibold text-lg flex items-center gap-2">
              Launch Demo
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
              </svg>
            </Link>
            <a href="#features" className="btn-ghost px-8 py-4 rounded-xl font-semibold text-lg">
              Learn More
            </a>
          </div>

          {/* Hero Visual */}
          <div className="relative max-w-5xl mx-auto">
            <div className="absolute inset-0 bg-gradient-to-t from-[#0a0a0b] via-transparent to-transparent z-10 pointer-events-none"></div>
            <div className="glass-card rounded-2xl p-8 text-left">
              <div className="flex items-center gap-3 mb-6">
                <div className="w-3 h-3 rounded-full bg-red-500"></div>
                <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
                <div className="w-3 h-3 rounded-full bg-green-500"></div>
                <span className="ml-4 text-sm text-gray-400">HomeOps Assistant</span>
              </div>
              <div className="space-y-4">
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center text-sm font-bold flex-shrink-0">U</div>
                  <div className="glass rounded-2xl rounded-tl-sm px-4 py-3 max-w-md">
                    <p>Is my washing machine still under warranty?</p>
                  </div>
                </div>
                <div className="flex gap-3 justify-end">
                  <div className="glass-card rounded-2xl rounded-tr-sm px-4 py-3 max-w-lg">
                    <p className="mb-2">Your <span className="text-violet-400">Washing Machine (AquaLine AL-7200)</span> is <span className="text-emerald-400 font-semibold">under warranty</span>.</p>
                    <p className="text-sm text-gray-400">Warranty ends: 2027-03-15 • Based on saved dates (not verified from manufacturer)</p>
                  </div>
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-emerald-500 to-cyan-600 flex items-center justify-center text-sm font-bold flex-shrink-0">AI</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="py-20 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-4xl md:text-5xl font-bold font-[family-name:var(--font-space-grotesk)] mb-4">
              Everything you need to <span className="gradient-text">stay on top</span>
            </h2>
            <p className="text-xl text-gray-400">Smart home maintenance made simple</p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[
              {
                icon: "🛠️",
                title: "Asset Tracking",
                description: "Keep track of all appliances, their details, purchase dates, and warranty information in one place."
              },
              {
                icon: "⏰",
                title: "Smart Reminders",
                description: "Get timely alerts for warranty expirations and scheduled maintenance before it's too late."
              },
              {
                icon: "📋",
                title: "Maintenance History",
                description: "Log repairs, issues, and services. Search through your complete home maintenance timeline."
              },
              {
                icon: "🧠",
                title: "AI Technician Briefs",
                description: "Generate comprehensive briefs for technicians using Amazon Bedrock AI, grounded in your actual records."
              },
              {
                icon: "🔗",
                title: "Provider Handoff",
                description: "Easily connect with service providers via Maps, WhatsApp, phone, or email with pre-filled messages."
              },
              {
                icon: "🔌",
                title: "MCP-Powered",
                description: "Built on Model Context Protocol for seamless integration with any MCP-compatible coding agent."
              }
            ].map((feature, i) => (
              <div key={i} className="glass-card rounded-2xl p-6">
                <div className="text-4xl mb-4">{feature.icon}</div>
                <h3 className="text-xl font-semibold mb-2 font-[family-name:var(--font-space-grotesk)]">{feature.title}</h3>
                <p className="text-gray-400 leading-relaxed">{feature.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Tech Stack */}
      <section id="tech" className="py-20 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-4xl md:text-5xl font-bold font-[family-name:var(--font-space-grotesk)] mb-4">
              Built with <span className="gradient-text">Modern Tech</span>
            </h2>
            <p className="text-xl text-gray-400">Enterprise-grade architecture</p>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {["Next.js 15", "TypeScript", "FastAPI", "MCP Protocol", "Amazon Bedrock", "PostgreSQL", "Docker", "Tailwind CSS"].map((tech, i) => (
              <div key={i} className="glass-card rounded-xl p-4 text-center font-medium">
                {tech}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 px-6">
        <div className="max-w-4xl mx-auto text-center glass-card rounded-3xl p-12">
          <h2 className="text-4xl md:text-5xl font-bold font-[family-name:var(--font-space-grotesk)] mb-6">
            Ready to take control of your <span className="gradient-text">home maintenance</span>?
          </h2>
          <p className="text-xl text-gray-400 mb-10">
            Try the interactive demo and see HomeOps in action
          </p>
          <Link href="/demo" className="btn-primary px-10 py-4 rounded-xl font-semibold text-lg inline-flex items-center gap-2">
            Start Free Demo
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-violet-500/20 py-8 px-6">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center font-bold text-sm">
              HO
            </div>
            <span className="font-semibold">HomeOps</span>
          </div>
          <p className="text-gray-400 text-sm">© 2026 HomeOps. Built for the Alexa+ Hackathon.</p>
        </div>
      </footer>
    </div>
  );
}
