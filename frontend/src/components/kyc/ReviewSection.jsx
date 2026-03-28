export function ReviewSection({ formData, illaka, misal, includeCoBorrower, includeGuarantor, isEdit, disbursementAmount, setDisbursementAmount }) {
  const PersonSummary = ({ title, data }) => {
    if (!data) return null;
    return (
      <div className="rounded-xl border border-border p-4 space-y-2">
        <h4 className="font-semibold text-foreground text-sm">{title}</h4>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div><span className="text-muted-foreground">Name:</span> <span className="font-medium">{data.name || "—"}</span></div>
          <div><span className="text-muted-foreground">Phone:</span> <span className="font-medium">{data.phone || "—"}</span></div>
          <div><span className="text-muted-foreground">DOB:</span> <span className="font-medium">{data.dob || "—"}</span></div>
          <div><span className="text-muted-foreground">Aadhaar:</span> <span className="font-medium">{data.aadhaar_number || "—"}</span></div>
          <div><span className="text-muted-foreground">Husband/Father:</span> <span className="font-medium">{data.relative_name || "—"}</span></div>
          <div className="col-span-2"><span className="text-muted-foreground">Address:</span> <span className="font-medium">{data.address || "—"}</span></div>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 pb-2 border-b border-border">
        <h3 className="text-lg font-bold font-['Outfit']">{isEdit ? "Review" : "Disbursement & Review"}</h3>
        <span className="text-sm text-muted-foreground">{isEdit ? "समीक्षा" : "वितरण और समीक्षा"}</span>
      </div>
      <div className="p-3 rounded-lg bg-primary/5 border border-primary/20 text-primary text-sm">
        <strong>Illaka:</strong> {illaka?.name || "—"} &nbsp;|&nbsp; <strong>Misal:</strong> {misal?.name || "—"}
      </div>

      {!isEdit && (
        <div className="bk-card bg-primary/5 border-primary/30 space-y-3">
          <div>
            <label className="bk-label"><span className="bk-label-en text-primary font-bold">Loan Disbursement Amount (₹)<span className="text-destructive">*</span></span><span className="bk-label-hi">वितरण राशि दर्ज करें</span></label>
            <input
              type="number"
              value={disbursementAmount}
              onChange={e => setDisbursementAmount(e.target.value)}
              className="bk-input text-xl font-bold"
              placeholder="e.g. 10300"
              min="1"
              data-testid="disbursement-amount-input"
            />
          </div>
          {disbursementAmount && !isNaN(parseFloat(disbursementAmount)) && parseFloat(disbursementAmount) > 0 && (() => {
            const p = parseFloat(disbursementAmount);
            const emi = Math.round(p * 1.17 / 12 / 100) * 100;
            const total = emi * 12;
            const interest = total - p;
            return (
              <div className="grid grid-cols-3 gap-3 pt-2 border-t border-primary/20">
                <div className="text-center">
                  <p className="text-xs text-muted-foreground">Monthly EMI</p>
                  <p className="text-lg font-bold text-primary font-['Outfit']">₹{emi.toLocaleString("en-IN")}</p>
                  <p className="text-xs text-muted-foreground">× 12 months</p>
                </div>
                <div className="text-center">
                  <p className="text-xs text-muted-foreground">Interest (17%)</p>
                  <p className="text-lg font-bold font-['Outfit']">₹{interest.toLocaleString("en-IN")}</p>
                </div>
                <div className="text-center">
                  <p className="text-xs text-muted-foreground">Total Repayable</p>
                  <p className="text-lg font-bold text-green-700 font-['Outfit']">₹{total.toLocaleString("en-IN")}</p>
                </div>
              </div>
            );
          })()}
        </div>
      )}

      <PersonSummary title="Primary Borrower / प्राथमिक उधारकर्ता" data={formData.primaryBorrower} />
      {includeCoBorrower && <PersonSummary title="Co-borrower / सह-उधारकर्ता" data={formData.coBorrower} />}
      {includeGuarantor && <PersonSummary title="Guarantor / गारंटर" data={formData.guarantor} />}
      <div className="flex gap-4 text-sm">
        <span className={formData.livePhotoPath ? "text-green-700" : "text-muted-foreground"}>
          {formData.livePhotoPath ? "✓" : "✗"} Live Photo
        </span>
        <span className={formData.gpsLocation ? "text-green-700" : "text-amber-600"}>
          {formData.gpsLocation ? "✓ GPS Captured" : "⏳ GPS pending..."}
        </span>
      </div>
    </div>
  );
}
