import { Box } from "@mui/material";
import type { BackgroundAsset } from "../utils/backgroundAssets";

/** Compact event brand art for auth / side surfaces. */
export default function EventBrandArt({ asset }: { asset: BackgroundAsset }) {
  return (
    <Box
      aria-hidden="true"
      sx={{
        position: "relative",
        width: "100%",
        aspectRatio: "1 / 1",
        borderRadius: "16px",
        overflow: "hidden",
        border: "1px solid rgba(23,33,28,0.10)",
        boxShadow: "0 2px 4px rgba(18,42,33,0.06), 0 12px 32px -12px rgba(13,53,41,0.16)",
        "@keyframes brandArtIn": {
          from: { opacity: 0, transform: "translateY(10px)" },
          to: { opacity: 1, transform: "translateY(0)" },
        },
        animation: "brandArtIn 360ms cubic-bezier(0.32, 0.72, 0, 1) both",
        "@media (prefers-reduced-motion: reduce)": {
          animation: "none",
        },
      }}
    >
      <Box
        component="img"
        src={asset.url}
        alt=""
        loading="lazy"
        decoding="async"
        sx={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
      />
      <Box
        sx={{
          position: "absolute",
          inset: 0,
          backgroundImage:
            "linear-gradient(180deg, transparent 55%, rgba(23,33,28,0.18) 100%), radial-gradient(120% 80% at 100% 0%, rgba(23,107,82,0.12), transparent 55%)",
          pointerEvents: "none",
        }}
      />
    </Box>
  );
}
