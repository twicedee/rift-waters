import numpy as np
import pandas as pd
import rasterio
from rasterio.merge import merge
from rasterio.warp import calculate_default_transform, reproject, Resampling
import matplotlib.pyplot as plt
from pathlib import Path
from scipy import ndimage, stats
from pyproj import CRS


class LakeExpansion:
    PERIMETER_RATIO_THRESHOLD = 2.0

    def __init__(self, region, dem_csv, sar_csv, seed_point=None):
        self.region = region
        self.dem_csv = dem_csv
        self.sar_csv = sar_csv
        self.seed_point = seed_point  # (row, col) in DEM array space
        self.base_dir = Path(f"./dataset/{region}")
        self.analysis_dir = self._ensure_directories()

        self.sar_df, self.dem_df, self.sar_paths, self.dem_tile_paths = self._readfiles()

        # populated by prepare_dem()
        self.dem_reprojected = None
        self.dem_transform = None
        self.dem_crs = None
        self.pixel_area_m2 = None

    def _readfiles(self):
        sar_df = pd.read_csv(self.sar_csv)
        dem_df = pd.read_csv(self.dem_csv)
        image_ids = sar_df["image_id"].tolist()

        sar_paths = {}
        for image_id in image_ids:
            sar_paths[image_id] = str(
                f"dataset/{self.region}/processed/sar_water_mask/{self.region}_{image_id}.tif"
            )

        dem_tile_paths = dem_df["dem_path"].tolist()
        
        print(f"{len(image_ids)} SAR water masks found for {self.region}")
        print(f"{len(dem_tile_paths)} DEM tiles found for {self.region}")
        print(f"DEM tiles: {dem_tile_paths[0]} ... {dem_tile_paths[-1]}")

        return sar_df, dem_df, sar_paths, dem_tile_paths

    def _ensure_directories(self):
        dir_path = self.base_dir / "analysis" / "lake_expansion"
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            return dir_path
        except Exception as e:
            print(f"Error creating directory {dir_path}: {e}")
            return None

    # ------------------------------------------------------------------
    # DEM prep
    # ------------------------------------------------------------------

    def read_dem_tiles(self):
        dem_srcs = [rasterio.open(p) for p in self.dem_tile_paths]
        dem_mosaic, dem_transform = merge(dem_srcs)
        dem_crs = dem_srcs[0].crs
        return dem_mosaic, dem_transform, dem_crs

    def reproject_dem_to_utm(self, dem_mosaic, dem_transform, dem_crs):
        if dem_crs.is_projected:
            # print(f"DEM is already projected: {dem_crs}")
            # dem_mosaic from rasterio.merge is (band, row, col) — keep 2D
            return dem_mosaic[0], dem_transform, dem_crs

        # print(f"DEM is in geographic coordinates: {dem_crs}. Reprojecting to UTM.")
        dem_bounds = rasterio.transform.array_bounds(
            dem_mosaic.shape[1], dem_mosaic.shape[2], dem_transform
        )
        centroid_lon = (dem_bounds[0] + dem_bounds[2]) / 2
        centroid_lat = (dem_bounds[1] + dem_bounds[3]) / 2

        utm_zone = int((centroid_lon + 180) / 6) + 1
        hemisphere_epsg_base = 32600 if centroid_lat >= 0 else 32700
        dst_crs = CRS.from_epsg(hemisphere_epsg_base + utm_zone)
        # print(f"Selected UTM CRS: {dst_crs}")

        dem_transform_new, dem_width_new, dem_height_new = calculate_default_transform(
            dem_crs, dst_crs, dem_mosaic.shape[2], dem_mosaic.shape[1], *dem_bounds
        )

        dem_reprojected = np.empty((dem_height_new, dem_width_new), dtype=dem_mosaic.dtype)
        reproject(
            source=dem_mosaic[0],
            destination=dem_reprojected,
            src_transform=dem_transform,
            src_crs=dem_crs,
            dst_transform=dem_transform_new,
            dst_crs=dst_crs,
            resampling=Resampling.bilinear,
        )

        # print(f"Reprojected DEM shape: {dem_reprojected.shape}")
        # print(f"Pixel size: {dem_transform_new.a:.2f} x {abs(dem_transform_new.e):.2f} m")
        return dem_reprojected, dem_transform_new, dst_crs

    def prepare_dem(self):
        """Mosaic + reproject DEM once, cache on the instance."""
        if self.dem_reprojected is not None:
            return self.dem_reprojected, self.dem_transform, self.dem_crs

        dem_mosaic, dem_transform, dem_crs = self.read_dem_tiles()
        dem_reprojected, dem_transform_new, dst_crs = self.reproject_dem_to_utm(
            dem_mosaic, dem_transform, dem_crs
        )

        self.dem_reprojected = dem_reprojected
        self.dem_transform = dem_transform_new
        self.dem_crs = dst_crs
        self.pixel_area_m2 = abs(dem_transform_new.a * dem_transform_new.e)
        # print(f"Pixel area: {self.pixel_area_m2:.2f} m^2")
        return dem_reprojected, dem_transform_new, dst_crs

    # ------------------------------------------------------------------
    # SAR mask alignment
    # ------------------------------------------------------------------

    def align_masks_to_dem(self):
        """Reproject every SAR water mask onto the DEM grid, once each."""
        dem_reprojected, dem_transform, dem_crs = self.prepare_dem()
        dst_shape = dem_reprojected.shape

        aligned_masks = {}
        for image_id, path in self.sar_paths.items():
            with rasterio.open(path) as src:
                aligned = np.empty(dst_shape, dtype=src.dtypes[0])
                reproject(
                    source=rasterio.band(src, 1),
                    destination=aligned,
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=dem_transform,
                    dst_crs=dem_crs,
                    resampling=Resampling.nearest,  # categorical mask — no interpolation
                )
            aligned_masks[image_id] = aligned

        self.aligned_masks = aligned_masks
        # print(f"Aligned {len(aligned_masks)} water masks to DEM grid, shape {dst_shape}")
        return aligned_masks

    # ------------------------------------------------------------------
    # WSE extraction
    # ------------------------------------------------------------------

    def extract_shoreline(self, water_mask, erosion_iterations=1):
        water_binary = water_mask == 1
        eroded = ndimage.binary_erosion(water_binary, iterations=erosion_iterations)
        return water_binary & ~eroded

    def estimate_wse(self, dem_array, shoreline_mask, percentile=50):
        elevations = dem_array[shoreline_mask]
        elevations = elevations[np.isfinite(elevations)]
        if elevations.size == 0:
            return np.nan
        return np.percentile(elevations, percentile)

    def compute_wse_table(self):
        """Per-date WSE, merged with SAR metadata, with outliers flagged."""
        dem_reprojected, _, _ = self.prepare_dem()
        if not hasattr(self, "aligned_masks"):
            self.align_masks_to_dem()

        wse_results = {}
        for image_id, mask in self.aligned_masks.items():
            shoreline = self.extract_shoreline(mask)
            wse = self.estimate_wse(dem_reprojected, shoreline)
            wse_results[image_id] = {
                "wse_m": wse,
                "shoreline_pixel_count": int(shoreline.sum()),
                "water_pixel_count": int((mask == 1).sum()),
            }

        wse_df = (
            pd.DataFrame.from_dict(wse_results, orient="index")
            .reset_index()
            .rename(columns={"index": "image_id"})
        )

        merged_df = wse_df.merge(self.sar_df, on="image_id", how="inner", suffixes=("", "_sar"))

        dropped_ids = set(self.sar_df["image_id"]) - set(wse_df["image_id"])
        if dropped_ids:
            print(f"Dropped {len(dropped_ids)} image_id(s) with no matching water mask: {sorted(dropped_ids)}")

        merged_df["date"] = pd.to_datetime(
            merged_df["image_id"].astype(str).str.extract(r"(\d{8})")[0], format="%Y%m%d"
        )
        merged_df = merged_df.sort_values("date").reset_index(drop=True)

        typical_perimeter = merged_df["boundary_perimeter_m"].median()
        merged_df["perimeter_ratio"] = merged_df["boundary_perimeter_m"] / typical_perimeter
        merged_df["is_outlier"] = merged_df["perimeter_ratio"] > self.PERIMETER_RATIO_THRESHOLD

        outliers = merged_df[merged_df["is_outlier"]][
            ["image_id", "date", "wse_m", "boundary_perimeter_m", "perimeter_ratio"]
        ]
        # print(f"Typical perimeter (median): {typical_perimeter:.0f} m")
        # print(f"Flagged {len(outliers)} outlier date(s):")
        # print(outliers)

        self.merged_df = merged_df
        # clean_df (outliers dropped) is the shared reference used downstream
        # by extent validation and volume estimation
        self.clean_df = merged_df[~merged_df["is_outlier"]].reset_index(drop=True)
        return merged_df

    # ------------------------------------------------------------------
    # Basin mask / seed point
    # ------------------------------------------------------------------

    def get_basin_mask(self, wse, seed_point=None):
        """Connected component of DEM cells below wse, touching seed_point."""
        seed_point = seed_point or self.seed_point
        if seed_point is None:
            raise ValueError("seed_point must be set — call derive_seed_point() first")

        dem_reprojected, _, _ = self.prepare_dem()
        below_wse = dem_reprojected < wse
        labeled, _ = ndimage.label(below_wse, structure=np.ones((3, 3)))
        seed_label = labeled[seed_point]
        if seed_label == 0:
            return np.zeros_like(below_wse, dtype=bool)
        return labeled == seed_label

    def derive_seed_point(self, sample_id=None):
        """Auto-derive a basin seed pixel from the median water pixel of a
        sample aligned SAR mask. Defaults to the first available image_id."""
        if not hasattr(self, "aligned_masks"):
            self.align_masks_to_dem()

        sample_id = sample_id or next(iter(self.aligned_masks))
        rows, cols = np.where(self.aligned_masks[sample_id] == 1)
        if rows.size == 0:
            raise ValueError(f"No water pixels found in aligned mask for image_id={sample_id}")

        seed_point = (int(np.median(rows)), int(np.median(cols)))
        # print(f"Using seed pixel: {seed_point} (from image_id={sample_id})")
        self.seed_point = seed_point
        return seed_point

    # ------------------------------------------------------------------
    # DEM/SAR extent cross-validation
    # ------------------------------------------------------------------

    def compute_extent_validation(self, seed_point=None):
        """Cross-validate SAR boundary extent against a DEM/WSE flood-fill
        basin, using only non-outlier dates (outliers dropped via sar_df's
        perimeter-ratio flag, computed in compute_wse_table)."""
        if not hasattr(self, "merged_df"):
            self.compute_wse_table()

        clean_df = self.clean_df
        dropped = self.merged_df["is_outlier"].sum()
        if dropped:
            print(f"Dropped {dropped} outlier date(s) before extent validation")

        seed_point = seed_point or self.seed_point or self.derive_seed_point()
        self.prepare_dem()

        extent_results = []
        for _, row in clean_df.iterrows():
            basin_mask = self.get_basin_mask(row["wse_m"], seed_point=seed_point)
            dem_area_m2 = basin_mask.sum() * self.pixel_area_m2
            extent_results.append(
                {
                    "image_id": row["image_id"],
                    "dem_extent_m2": dem_area_m2,
                    "sar_extent_m2": row["boundary_area_m2"],
                    "pct_diff": 100 * (dem_area_m2 - row["boundary_area_m2"]) / row["boundary_area_m2"],
                }
            )

        extent_df = pd.DataFrame(extent_results)
        self.extent_df = extent_df
        return extent_df

    # ------------------------------------------------------------------
    # Volume estimation
    # ------------------------------------------------------------------

    def get_dry_land_baseline(self, basin_masks_by_date, baseline_index=0):
        """Dry land relative to the earliest clean date's basin — NOT an
        all-time union, which collapses every volume estimate to zero
        (a pixel wet on any date can never be dry-at-baseline under a union)."""
        return ~basin_masks_by_date[baseline_index]

    def estimate_volume(self, basin_mask, wse, dry_land_mask):
        dem_reprojected, _, _ = self.prepare_dem()
        expansion_mask = basin_mask & dry_land_mask
        depths = np.clip(wse - dem_reprojected[expansion_mask], 0, None)
        return np.sum(depths) * self.pixel_area_m2, int(expansion_mask.sum())

    def compute_volume_table(self, seed_point=None):
        if not hasattr(self, "merged_df"):
            self.compute_wse_table()

        clean_df = self.clean_df
        seed_point = seed_point or self.seed_point or self.derive_seed_point()

        basin_masks_by_date = [
            self.get_basin_mask(row["wse_m"], seed_point=seed_point) for _, row in clean_df.iterrows()
        ]
        dry_land_baseline = self.get_dry_land_baseline(basin_masks_by_date, baseline_index=0)

        volume_results = []
        for i, row in clean_df.iterrows():
            volume_m3, expansion_px = self.estimate_volume(
                basin_masks_by_date[i], row["wse_m"], dry_land_baseline
            )
            volume_results.append(
                {
                    "image_id": row["image_id"],
                    "date": row["date"],
                    "wse_m": row["wse_m"],
                    "expansion_volume_m3": volume_m3,
                    "expansion_pixel_count": expansion_px,
                }
            )

        volume_df = pd.DataFrame(volume_results)
        # print(f"Non-zero count: {(volume_df['expansion_volume_m3'] != 0).sum()} / {len(volume_df)}")
        # print(volume_df.describe())

        self.volume_df = volume_df
        self.basin_masks_clean = basin_masks_by_date
        return volume_df

    # ------------------------------------------------------------------
    # Summary + persistence
    # ------------------------------------------------------------------

    def build_summary_table(self):
        if not hasattr(self, "volume_df"):
            self.compute_volume_table()

        summary_df = self.merged_df[
            ["image_id", "date", "wse_m", "boundary_area_m2", "boundary_perimeter_m", "perimeter_ratio", "is_outlier"]
        ].merge(
            self.volume_df[["image_id", "expansion_volume_m3", "expansion_pixel_count"]],
            on="image_id",
            how="left",
        )

        if hasattr(self, "extent_df"):
            summary_df = summary_df.merge(
                self.extent_df[["image_id", "dem_extent_m2", "pct_diff"]], on="image_id", how="left"
            )

        summary_df["excluded_from_volume_calc"] = summary_df["is_outlier"]
        self.summary_df = summary_df

        csv_path = self.analysis_dir / f"{self.region}_expansion_summary.csv"
        summary_df.to_csv(csv_path, index=False)
        print(f"  📝 Summary saved to {csv_path}")
        return summary_df

    # ------------------------------------------------------------------
    # Plots
    # ------------------------------------------------------------------

    def _trend_df(self):
        plot_df = self.summary_df[~self.summary_df["is_outlier"]].reset_index(drop=True).copy()
        plot_df["days_since_start"] = (plot_df["date"] - plot_df["date"].min()).dt.days
        plot_df["years_since_start"] = plot_df["days_since_start"] / 365.25
        return plot_df

    def plot_surface_area_trend(self):
        plot_df = self._trend_df()
        slope, intercept, r, p, _ = stats.linregress(plot_df["years_since_start"], plot_df["boundary_area_m2"])
        trend = intercept + slope * plot_df["years_since_start"]
        # print(f"Extent trend: {slope:,.0f} m²/year (R²={r**2:.3f}, p={p:.4f})")

        fig, ax = plt.subplots(figsize=(11, 5))
        ax.scatter(plot_df["date"], plot_df["boundary_area_m2"], s=20, color="steelblue", alpha=0.6, label="Observed extent")
        ax.plot(plot_df["date"], trend, color="darkorange", linewidth=2, label=f"Trend: {slope:,.0f} m²/yr")
        ax.set_ylabel("Lake surface area (m²)")
        ax.set_xlabel("Date")
        ax.set_title(f"Lake {self.region.title()} — Surface Area Over Time (SAR-derived, outliers excluded)")
        ax.ticklabel_format(axis="y", style="plain")
        ax.legend()
        ax.grid(alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()
        out_path = self.analysis_dir / "surface_area_trend.png"
        plt.savefig(out_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        # print(f"  📈 Saved {out_path}")

    def plot_wse_trend(self):
        plot_df = self._trend_df()
        slope, intercept, r, p, _ = stats.linregress(plot_df["years_since_start"], plot_df["wse_m"])
        trend = intercept + slope * plot_df["years_since_start"]
        print(f"WSE trend: {slope:.4f} m/year (R²={r**2:.3f}, p={p:.4f})")

        fig, ax = plt.subplots(figsize=(11, 5))
        ax.scatter(plot_df["date"], plot_df["wse_m"], s=20, color="steelblue", alpha=0.6, label="Observed WSE")
        ax.plot(plot_df["date"], trend, color="darkorange", linewidth=2, label=f"Trend: {slope:.4f} m/yr")
        ax.set_ylabel("Water surface elevation (m)")
        ax.set_xlabel("Date")
        ax.set_title(f"Lake {self.region.title()} — Water Surface Elevation Over Time (outliers excluded)")
        ax.legend()
        ax.grid(alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()
        out_path = self.analysis_dir / "wse_trend.png"
        plt.savefig(out_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        # print(f"  📈 Saved {out_path}")

    def plot_cumulative_surface_area_change(self):
        plot_df = self._trend_df()
        baseline_extent = plot_df["boundary_area_m2"].iloc[0]
        plot_df["cumulative_expansion_m2"] = plot_df["boundary_area_m2"] - baseline_extent

        fig, ax = plt.subplots(figsize=(11, 5))
        ax.fill_between(
            plot_df["date"], plot_df["cumulative_expansion_m2"], 0,
            where=(plot_df["cumulative_expansion_m2"] >= 0), color="teal", alpha=0.3, interpolate=True,
        )
        ax.fill_between(
            plot_df["date"], plot_df["cumulative_expansion_m2"], 0,
            where=(plot_df["cumulative_expansion_m2"] < 0), color="firebrick", alpha=0.3, interpolate=True,
        )
        ax.plot(plot_df["date"], plot_df["cumulative_expansion_m2"], color="black", linewidth=1)
        ax.axhline(0, color="gray", linestyle="--", linewidth=1)
        ax.set_ylabel(f"Change in surface area since {plot_df['date'].iloc[0].date()} (m²)")
        ax.set_xlabel("Date")
        ax.set_title(f"Lake {self.region.title()} — Cumulative Surface Area Change")
        ax.ticklabel_format(axis="y", style="plain")
        ax.grid(alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()
        out_path = self.analysis_dir / "cumulative_surface_area_change.png"
        plt.savefig(out_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        # print(f"  📈 Saved {out_path}")

    def plot_expansion_volume(self):
        volume_df = self.volume_df.copy()
        baseline_date = self.clean_df["date"].iloc[0]
        volume_df["years_since_start"] = (volume_df["date"] - volume_df["date"].min()).dt.days / 365.25

        slope, intercept, r, p, _ = stats.linregress(volume_df["years_since_start"], volume_df["expansion_volume_m3"])
        trend = intercept + slope * volume_df["years_since_start"]
        # print(f"Volume trend: {slope:,.0f} m³/year (R²={r**2:.3f}, p={p:.4f})")

        fig, ax = plt.subplots(figsize=(11, 5))
        ax.scatter(volume_df["date"], volume_df["expansion_volume_m3"], s=20, color="teal", alpha=0.6, label="Expansion volume")
        ax.plot(volume_df["date"], trend, color="darkorange", linewidth=2, label=f"Trend: {slope:,.0f} m³/yr")
        ax.axhline(0, color="gray", linestyle="--", linewidth=1)
        ax.set_ylabel(f"Expansion volume since {baseline_date.date()} (m³)")
        ax.set_xlabel("Date")
        ax.set_title(f"Lake {self.region.title()} — Expansion Volume Relative to Earliest Observed Extent")
        ax.ticklabel_format(axis="y", style="plain")
        ax.legend()
        ax.grid(alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()
        out_path = self.analysis_dir / "expansion_volume_vs_baseline.png"
        plt.savefig(out_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        # print(f"  📈 Saved {out_path}")

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def run_full_analysis(self, seed_point=None):
        self.compute_wse_table()
        self.compute_extent_validation(seed_point=seed_point)
        self.compute_volume_table(seed_point=seed_point)
        self.build_summary_table()
        self.plot_surface_area_trend()
        self.plot_wse_trend()
        self.plot_cumulative_surface_area_change()
        self.plot_expansion_volume()
        return self.summary_df
    
    
analyzer = LakeExpansion("nakuru", "dataset/nakuru/metadata/nakuru_GLO30.csv", "dataset/nakuru/metadata/nakuru_sar.csv")
analyzer.run_full_analysis()