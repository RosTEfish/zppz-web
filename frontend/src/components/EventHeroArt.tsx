import { Box } from "@mui/material";
import { useEventTheme } from "../contexts/EventThemeProvider";
import type { BackgroundAsset } from "../utils/backgroundAssets";

/** Full-bleed event art for the home hero; washes follow dynamic event palette. */
export default function EventHeroArt({ asset }: { asset: BackgroundAsset }) {
  const { palette } = useEventTheme();
  return (
    <Box
      aria-hidden="true"
      sx={{
        position: "absolute",
        inset: 0,
        pointerEvents: "none",
        overflow: "hidden",
        "@keyframes heroArtIn": {
          from: { opacity: 0, transform: "scale(1.04)" },
          to: { opacity: 1, transform: "scale(1)" },
        },
        "@media (prefers-reduced-motion: reduce)": {
          "& img": { animation: "none !important" },
        },
      }}
    >
      <Box
        component="img"
        src={asset.url}
        alt=""
        loading="eager"
        decoding="async"
        sx={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          objectFit: "cover",
          objectPosition: { xs: "center 35%", md: "78% center" },
          animation: "heroArtIn 420ms cubic-bezier(0.32, 0.72, 0, 1) both",
        }}
      />
      <Box
        sx={{
          position: "absolute",
          inset: 0,
          backgroundImage: {
            xs: [
              "linear-gradient(180deg, rgba(247,247,244,0.94) 0%, rgba(247,247,244,0.88) 42%, rgba(247,247,244,0.72) 100%)",
              `radial-gradient(520px 260px at 78% 0%, ${palette.accentSoft}, transparent 62%)`,
              `radial-gradient(680px 320px at 96% 100%, ${palette.washA}, transparent 58%)`,
            ].join(", "),
            md: [
              "linear-gradient(105deg, rgba(247,247,244,0.97) 0%, rgba(247,247,244,0.92) 38%, rgba(247,247,244,0.55) 62%, rgba(247,247,244,0.22) 100%)",
              `radial-gradient(520px 260px at 78% 0%, ${palette.accentSoft}, transparent 62%)`,
              `radial-gradient(680px 320px at 96% 100%, ${palette.washA}, transparent 58%)`,
            ].join(", "),
          },
        }}
      />
    </Box>
  );
}
