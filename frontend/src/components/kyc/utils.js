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

// Suffix → Hindi display mapping
export const SUFFIX_HINDI_MAP = {
  Dhobi: "धोबी", Darji: "दर्जी", Kumhar: "कुम्हार", Lohar: "लोहार",
  Teli: "तेली", Nai: "नाई", Kori: "कोरी", Mallah: "मल्लाह",
  Kewat: "केवट", Kahar: "कहार", Yadav: "यादव", Maurya: "मौर्य",
  Prajapati: "प्रजापति", Kushwaha: "कुशवाहा", Pasi: "पासी", Bind: "बिंद",
  Rajput: "राजपूत", Thakur: "ठाकुर", Sharma: "शर्मा", Gupta: "गुप्त",
  Dubey: "दुबे", Mishra: "मिश्रा", Chamar: "चमार",
};

/** Returns the Hindi equivalent of a suffix string. */
export const getSuffixHindi = (suffix) => {
  if (!suffix) return "";
  if (suffix.startsWith("Urf ")) return "उर्फ़ " + suffix.substring(4);
  return SUFFIX_HINDI_MAP[suffix] || suffix;
};

export const emptyPerson = {
  phone: "", name: "", name_hindi: "", suffix: "", dob: "", address: "",
  relative_name: "", relative_name_hindi: "", gender: "",
  aadhaar_number: "", aadhaar_front_path: null, aadhaar_back_path: null,
  document_type: "voter_id", document_front_path: null, document_back_path: null,
  phone_history: [],
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
