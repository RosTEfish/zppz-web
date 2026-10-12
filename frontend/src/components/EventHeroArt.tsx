import { Box } from "@mui/material";
import { useEventTheme } from "../contexts/EventThemeProvider";
import type { BackgroundAsset } from "../utils/backgroundAssets";

/** Full-bleed event art for the home hero; ink-wash veils follow canvas readability. */
export default function EventHeroArt({
  asset,
  largeAsset = null,
  animate = true,
}: {
  asset: BackgroundAsset;
  /** Optional higher-res art for wide viewports (typically post when hero is banner). */
  largeAsset?: BackgroundAsset | null;
  animate?: boolean;
}) {
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
      <picture style={{ position: "absolute", inset: 0, display: "block", width: "100%", height: "100%" }}>
        {largeAsset ? <source media="(min-width: 900px)" srcSet={largeAsset.url} type="image/webp" /> : null}
        <Box
          component="img"
          src={asset.url}
          alt=""
          width={960}
          height={300}
          loading="eager"
          decoding="async"
          fetchPriority="high"
          sx={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            objectFit: "cover",
            objectPosition: { xs: "62% 30%", md: "72% 42%" },
            animation: animate ? "heroArtIn 420ms cubic-bezier(0.32, 0.72, 0, 1) both" : "none",
          }}
        />
      </picture>
      <Box
        sx={{
          position: "absolute",
          inset: 0,
          backgroundImage: {
            xs: [
              "linear-gradient(180deg, rgba(250,251,250,0.2) 0%, rgba(250,251,250,0.55) 42%, rgba(250,251,250,0.96) 72%, #FAFBFA 100%)",
              `radial-gradient(420px 240px at 70% 18%, ${palette.tint}66, transparent 70%)`,
            ].join(", "),
            md: [
              "linear-gradient(105deg, rgba(250,251,250,0.92) 0%, rgba(250,251,250,0.78) 34%, rgba(250,251,250,0.28) 58%, rgba(250,251,250,0.06) 100%)",
              `radial-gradient(520px 280px at 18% 20%, ${palette.tint}73, transparent 70%)`,
            ].join(", "),
          },
        }}
      />
    </Box>
  );
}
