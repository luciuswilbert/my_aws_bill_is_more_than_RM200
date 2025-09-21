"use client"

import { useState } from "react"
import { VideoUploadStep } from "@/components/video-upload-step"
import { TranslationResultsStep } from "@/components/translation-results-step"

export default function HomePage() {
  const [currentStep, setCurrentStep] = useState<"upload" | "results">("upload")
  const [translationData, setTranslationData] = useState(null)

  const handleTranslationComplete = (data) => {
    setTranslationData(data)
    setCurrentStep("results")
  }

  const handleBackToUpload = () => {
    setCurrentStep("upload")
    setTranslationData(null)
  }

  return (
    <main className="min-h-screen bg-background">
      {currentStep === "upload" && <VideoUploadStep onTranslationComplete={handleTranslationComplete} />}
      {currentStep === "results" && translationData && (
        <TranslationResultsStep data={translationData} onBackToUpload={handleBackToUpload} />
      )}
    </main>
  )
}
