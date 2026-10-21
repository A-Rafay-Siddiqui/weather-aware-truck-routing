// Mirrors the JSON produced by backend/planner/services/planner.py and heatmap.py.

export type RiskKey = 'low' | 'moderate' | 'high' | 'severe' | 'no_travel';
export type WeatherSource = 'live' | 'simulated';
export type SampleInterval = 10 | 25 | 50;

export interface Place {
  label: string;
  lat: number;
  lon: number;
}

export interface PlanInput {
  origin: Place;
  destination: Place;
  departure_time: string; // ISO 8601 with offset
  load_weight_lbs: number;
  sample_interval_miles: SampleInterval;
  weather_source: WeatherSource;
  include_hos: boolean;
}

export interface CheckpointWeather {
  wind_mph: number;
  gust_mph: number | null;
  rain_in_hr: number;
  snow_in_hr: number;
  weather_code: number | null;
}

export interface CheckpointRisk {
  level: RiskKey;
  score: number;
  wind: RiskKey;
  rain: RiskKey;
  snow: RiskKey;
  load_rule_applied: boolean;
  factors: string[];
}

export interface Checkpoint {
  index: number;
  mile: number;
  lat: number;
  lon: number;
  segment: [number, number];
  drive_offset_s: number;
  eta_offset_s: number;
  eta: string;
  weather: CheckpointWeather;
  risk: CheckpointRisk;
}

export interface Stop {
  kind: 'break' | 'rest';
  mile: number;
  lat: number;
  lon: number;
  start_offset_s: number;
  duration_s: number;
}

/** [lon, lat, seconds after departure, mile] */
export type PathPoint = [number, number, number, number];

export interface RouteResult {
  id: string;
  name: string;
  strategy: string;
  roads: string[];
  rank: number;
  recommended: boolean;
  distance_miles: number;
  drive_time_s: number;
  travel_time_s: number;
  traffic_delay_s: number;
  departure_time: string;
  arrival_time: string;
  risk: {
    max_level: RiskKey;
    average_score: number;
    miles_by_level: Record<RiskKey, number>;
  };
  bbox: [number, number, number, number];
  path: PathPoint[];
  stops: Stop[];
  checkpoints: Checkpoint[];
}

export interface Recommendation {
  route_id: string;
  headline: string;
  reasons: string[];
  warnings: string[];
  criteria: string[];
}

export interface Plan {
  id: string;
  created_at: string;
  request: PlanInput;
  recommended_route_id: string;
  recommendation: Recommendation;
  routes: RouteResult[];
  bbox: [number, number, number, number];
  simulation: unknown | null;
  generated_at: string;
}

export interface PlanSummary {
  id: string;
  created_at: string;
  origin: string;
  destination: string;
  departure_time: string;
  weather_source: WeatherSource;
}

export interface Heatmap {
  cell_deg: number;
  cols: number;
  rows: number;
  west: number;
  east: number;
  north: number;
  south: number;
  start_time: string;
  hours: number;
  cells: [number, number][];
  centers: [number, number][];
  wind_mph: number[][];
  rain_in_hr: number[][];
  snow_in_hr: number[][];
  risk: number[][];
}

export interface Threshold {
  level: RiskKey;
  min: number;
  inclusive: boolean;
}

export interface RiskRules {
  levels: { key: RiskKey; label: string; score: number }[];
  wind_mph: Threshold[];
  rain_in_hr: Threshold[];
  snow_in_hr: Threshold[];
  load_rules: {
    min_wind_mph: number;
    max_wind_mph: number;
    min_load_lbs: number;
    level: RiskKey;
    description: string;
  }[];
}
