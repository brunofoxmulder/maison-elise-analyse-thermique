from dataclasses import replace


def filter_outdoor_temperature_anomalies(samples, cfg):
    cleaned, anomalies = [], []
    prev_raw = None
    for sample in samples:
        value = sample.temp_outdoor_ref
        rejected = False
        if value is not None and prev_raw is not None and prev_raw.temp_outdoor_ref is not None:
            minutes = (sample.ts - prev_raw.ts).total_seconds() / 60.0
            if 0 < minutes <= 7.5:
                jump = abs(value - prev_raw.temp_outdoor_ref)
                if jump > cfg.outdoor_reject_jump_c_per_5min:
                    rejected = True
                    anomalies.append({"ts":sample.ts.isoformat(),"type":"outdoor_temperature_jump_rejected","value":value,"previous":prev_raw.temp_outdoor_ref,"jump_c":round(jump,2),"rejected":True})
                elif jump > cfg.outdoor_flag_jump_c_per_5min:
                    anomalies.append({"ts":sample.ts.isoformat(),"type":"outdoor_temperature_step_suspect","value":value,"previous":prev_raw.temp_outdoor_ref,"jump_c":round(jump,2),"rejected":False})
        cleaned.append(replace(sample, temp_outdoor_ref=None) if rejected else sample)
        if value is not None: prev_raw = sample
    return cleaned, anomalies
