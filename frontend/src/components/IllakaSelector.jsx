import { useState } from "react";
import { MapPin, Globe, Check, ArrowRight, Loader2 } from "lucide-react";
import { useIllaka } from "./IllakaContext";
import { useAuth } from "./AuthContext";

export default function IllakaSelector() {
  const { user } = useAuth();
  const { filteredIllakas, setSelectedIllaka, selectedMaalik } = useIllaka();
  // undefined = not yet chosen in this UI, null = "All", {id,name} = specific
  const [choice, setChoice] = useState(undefined);

  const handleContinue = () => {
    if (choice === undefined) return;
    setSelectedIllaka(choice);
  };

  const isAllChosen = choice === null;

  const greeting = () => {
    const h = new Date().getHours();
    if (h < 12) return "सुप्रभात";
    if (h < 17) return "नमस्कार";
    return "शुभ संध्या";
  };

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Green Header */}
      <div className="px-6 py-8" style={{ background: "hsl(156, 72%, 25%)" }}>
        <div className="max-w-2xl mx-auto">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center">
              <span className="text-white font-bold text-lg font-['Outfit']">B</span>
            </div>
            <div>
              <h1 className="font-bold text-xl text-white font-['Outfit']">Bahi Khata</h1>
              <p className="text-white/60 text-xs">NBFC-MFI Platform</p>
            </div>
          </div>
          <div>
            <p className="text-white/70 text-sm mb-1">{greeting()}, {user?.name?.split(" ")[0]}</p>
            <h2 className="text-white text-2xl font-bold font-['Outfit']">Select Working Illaka</h2>
            <p className="text-white/60 text-sm mt-1">इस सत्र के लिए अपना इलाका चुनें</p>
          </div>
        </div>
      </div>

      {/* Cards */}
      <div className="flex-1 p-5 max-w-2xl mx-auto w-full">
        {filteredIllakas.length === 0 ? (
          <div className="flex items-center justify-center pt-16">
            <Loader2 size={24} className="animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="space-y-3 mt-2">
            {/* All Illakas card */}
            <button
              onClick={() => setChoice(null)}
              data-testid="illaka-choice-all"
              className={`w-full flex items-center gap-4 p-4 rounded-xl border-2 transition-all text-left ${
                isAllChosen
                  ? "border-primary bg-primary/8 shadow-sm"
                  : "border-border bg-card hover:border-primary/40 hover:shadow-sm"
              }`}
            >
              <div
                className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${
                  isAllChosen ? "bg-primary" : "bg-muted"
                }`}
              >
                <Globe size={20} className={isAllChosen ? "text-white" : "text-muted-foreground"} />
              </div>
              <div className="flex-1">
                <p className={`font-semibold text-sm ${isAllChosen ? "text-primary" : "text-foreground"}`}>
                  {selectedMaalik ? `All of ${selectedMaalik.name}'s Illakas` : "All Illakas / सभी इलाके"}
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {selectedMaalik ? `View all data for ${selectedMaalik.name}` : "View data across all assigned areas"}
                </p>
              </div>
              {isAllChosen && (
                <div className="w-6 h-6 rounded-full bg-primary flex items-center justify-center flex-shrink-0">
                  <Check size={13} className="text-white" />
                </div>
              )}
            </button>

            {/* Individual Illakas */}
            {filteredIllakas.map((ill, idx) => {
              const isChosen = choice?.id === ill.id;
              return (
                <button
                  key={ill.id}
                  onClick={() => setChoice({ id: ill.id, name: ill.name })}
                  data-testid={`illaka-choice-${ill.id}`}
                  className={`w-full flex items-center gap-4 p-4 rounded-xl border-2 transition-all text-left ${
                    isChosen
                      ? "border-primary bg-primary/8 shadow-sm"
                      : "border-border bg-card hover:border-primary/40 hover:shadow-sm"
                  }`}
                >
                  <div
                    className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${
                      isChosen ? "bg-primary" : "bg-muted"
                    }`}
                  >
                    <MapPin size={20} className={isChosen ? "text-white" : "text-muted-foreground"} />
                  </div>
                  <div className="flex-1">
                    <p className={`font-semibold text-sm ${isChosen ? "text-primary" : "text-foreground"}`}>
                      {ill.name}
                    </p>
                    {ill.description && (
                      <p className="text-xs text-muted-foreground mt-0.5">{ill.description}</p>
                    )}
                  </div>
                  {isChosen && (
                    <div className="w-6 h-6 rounded-full bg-primary flex items-center justify-center flex-shrink-0">
                      <Check size={13} className="text-white" />
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        )}

        {/* Continue Button */}
        <div className="mt-6 pb-6">
          <button
            onClick={handleContinue}
            disabled={choice === undefined}
            data-testid="illaka-continue-btn"
            className={`w-full flex items-center justify-center gap-2 py-3.5 rounded-xl font-semibold text-sm transition-all ${
              choice === undefined
                ? "bg-muted text-muted-foreground cursor-not-allowed"
                : "bk-btn-primary"
            }`}
          >
            {choice === undefined ? (
              "Select an Illaka to continue / इलाका चुनें"
            ) : (
              <>
                Continue
                <span className="text-xs opacity-80">
                  / {choice === null ? (selectedMaalik ? `All - ${selectedMaalik.name}` : "सभी इलाके") : choice.name}
                </span>
                <ArrowRight size={16} />
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
