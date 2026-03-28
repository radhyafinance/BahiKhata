// Shared utilities for the KYC Form components
export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const STEPS = [
  { id: 1, title: "Illaka & Misal", titleHi: "इलाका और मिसाल" },
  { id: 2, title: "Primary Borrower", titleHi: "प्राथमिक उधारकर्ता" },
  { id: 3, title: "Co-borrower", titleHi: "सह-उधारकर्ता" },
  { id: 4, title: "Guarantor", titleHi: "गारंटर" },
  { id: 5, title: "Live Photo & GPS", titleHi: "लाइव फोटो और GPS" },
  { id: 6, title: "Review & Submit", titleHi: "समीक्षा और जमा करें" },
];

export const emptyPerson = {
  phone: "", name: "", name_hindi: "", dob: "", address: "",
  relative_name: "", relative_name_hindi: "", gender: "",
  aadhaar_number: "", aadhaar_front_path: null, aadhaar_back_path: null,
  document_type: "voter_id", document_front_path: null, document_back_path: null,
};

export async function compressImage(file, maxWidth = 1200, quality = 0.72) {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      let w = img.naturalWidth, h = img.naturalHeight;
      if (w > maxWidth) { h = Math.round((h * maxWidth) / w); w = maxWidth; }
      const canvas = document.createElement("canvas");
      canvas.width = w; canvas.height = h;
      canvas.getContext("2d").drawImage(img, 0, 0, w, h);
      canvas.toBlob(
        (blob) => resolve(blob ? new File([blob], "img.jpg", { type: "image/jpeg" }) : file),
        "image/jpeg", quality
      );
    };
    img.onerror = () => resolve(file);
    img.src = url;
  });
}
