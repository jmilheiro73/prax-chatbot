/** Cartão do resultado do `get_weather`: ícone pela condição e a temperatura em destaque. */

export interface Weather {
  city: string;
  temp_c: number;
  condition: string;
}

type Sky = "clear" | "partly" | "cloudy" | "rain" | "storm" | "snow" | "fog";

// A ordem importa: "pancadas de chuva com sol" é chuva, e "parcialmente nublado" não é só "nublado".
const SKY_PATTERNS: Array<[RegExp, Sky]> = [
  [/tempest|trovoada|temporal|\braios?\b/i, "storm"],
  [/chuv|garoa|pancada/i, "rain"],
  [/nevoeiro|neblina|n[eé]voa|bruma/i, "fog"],
  [/neve|nevasca|nevando/i, "snow"],
  [/parcial|poucas nuvens|entre nuvens|sol com nuvens|sol e nuvens/i, "partly"],
  [/nublado|encoberto|nuvens/i, "cloudy"],
  [/\bsol\b|limpo|claro|ensolarado/i, "clear"],
];

function skyOf(condition: string): Sky {
  return SKY_PATTERNS.find(([pattern]) => pattern.test(condition))?.[1] ?? "cloudy";
}

export function isWeather(value: unknown): value is Weather {
  const v = value as Partial<Weather> | null;
  return typeof v?.city === "string" && typeof v.temp_c === "number" && typeof v.condition === "string";
}

export function WeatherCard({ weather }: { weather: Weather }) {
  const sky = skyOf(weather.condition);
  return (
    <div className="weather" data-sky={sky}>
      <div>
        <p className="wx-city">{weather.city}</p>
        <p className="wx-temp">{Math.round(weather.temp_c)}°C</p>
        <p className="wx-condition">{weather.condition.charAt(0).toUpperCase() + weather.condition.slice(1)}</p>
      </div>
      <SkyIcon sky={sky} />
    </div>
  );
}

const CLOUD = "M46 44H20a10 10 0 0 1-1.6-19.87A14 14 0 0 1 45.2 22.1 11 11 0 0 1 46 44z";

function Sun({ cx, cy, r }: { cx: number; cy: number; r: number }) {
  return (
    <g className="wx-sun" fill="#ffc53d" stroke="#ffc53d" strokeWidth={r / 3.5} strokeLinecap="round">
      <circle cx={cx} cy={cy} r={r} stroke="none" />
      {[0, 45, 90, 135, 180, 225, 270, 315].map((a) => (
        <line key={a} x1={cx} y1={cy - r * 1.4} x2={cx} y2={cy - r * 1.8} transform={`rotate(${a} ${cx} ${cy})`} />
      ))}
    </g>
  );
}

/** Três gotas ou flocos caindo, cada um com um atraso. */
function Falling({ color, r }: { color: string; r: number }) {
  return (
    <g fill={color}>
      {[22, 33, 44].map((x, i) => (
        <ellipse key={x} className="wx-fall" style={{ animationDelay: `${i * 0.3}s` }} cx={x} cy={52} rx={r} ry={r === 3 ? 3 : 4} />
      ))}
    </g>
  );
}

function SkyIcon({ sky }: { sky: Sky }) {
  return (
    <svg className="wx-icon" viewBox="0 0 64 64" aria-hidden>
      {sky === "clear" && <Sun cx={32} cy={32} r={13} />}
      {sky === "partly" && (
        <>
          <Sun cx={43} cy={19} r={9} />
          <path d={CLOUD} fill="#f4f7fb" transform="translate(-3 6)" />
        </>
      )}
      {sky === "cloudy" && (
        <>
          <path d={CLOUD} fill="#b9c4d1" transform="translate(9 -5) scale(.8)" />
          <path d={CLOUD} fill="#f4f7fb" transform="translate(-3 6)" />
        </>
      )}
      {sky === "rain" && (
        <>
          <path d={CLOUD} fill="#dbe3ec" transform="translate(-1 -6)" />
          <Falling color="#7cc4ff" r={2} />
        </>
      )}
      {sky === "storm" && (
        <>
          <path d={CLOUD} fill="#aeb8c6" transform="translate(-1 -8)" />
          <path d="M35 34 26 47h6l-3 12 11-15h-6l4-10z" fill="#ffd54a" />
        </>
      )}
      {sky === "snow" && (
        <>
          <path d={CLOUD} fill="#f4f7fb" transform="translate(-1 -6)" />
          <Falling color="#ffffff" r={3} />
        </>
      )}
      {sky === "fog" && (
        <>
          <path d={CLOUD} fill="#dbe3ec" transform="translate(-1 -8)" />
          <path d="M14 45h36M19 52h26" stroke="#dbe3ec" strokeWidth={3.5} strokeLinecap="round" />
        </>
      )}
    </svg>
  );
}
