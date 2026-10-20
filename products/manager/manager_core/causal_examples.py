"""L005: an intentionally confounded, entirely synthetic toy population."""


def confounded_toy():
    # Motivated participants select mornings; label morning has no causal effect.
    # morning: 18 motivated + 2 unmotivated / evening: 2 motivated +18 unmotivated
    morning=[1]*18+[0]*2
    evening=[1]*2+[0]*18
    observed_gap=sum(morning)/len(morning)-sum(evening)/len(evening)
    return {'observed_gap':observed_gap,
            'oracle_effect_of_changing_label':0.0,
            'synthetic_only':True,
            'confounder':'motivation affects both timing and walking'}
