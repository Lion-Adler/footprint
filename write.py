






@njit(cache = True)
def _build_fp_core(prices, sizes, is_buy_arr, tick_size):
    n = len(prices)
    if n = 0:
        empty = np.zeros(1,dtype = np.float64)
        return empty, empty , empty 

    p_min = math.floor(prices[0]/ tick_size + 0.5) * tick_size 
    p_max = p_min 
    for i in range(n):
        qp = math.floor(prices[i]/tick_size + 0.5) * tick_size 
        if qp < p_min:
            p_min = qp 
        if qp > p_max:
            p_pax = qp 

    n_levels = int(round((p_max-p_min)/tick_size)) + 1 

    if n_levels > 100_000:
        n_levels = 100000

    levels   =np.empty(n_levels,dtype=np.float64)
    ask_vols =np.zeros(n_levels,dtype=np.float64)
    bid_vols =np.zeros(n_levels,dtype=np.float64)

    for i in range(n_levels):
        levels[i] = p_min + i* tick_size 

    for i in range(n):
        qp = math.floor(prices[i] / tick_size + 0.5) * tick_size 
        idx = int(round((qp - p_min)/ tick_size))

        if 0 <= idx < n_levels:
            if is_buy_arr[i]:
                ask_vols[idx] += sizes[i]
            else:
                bid_vols[idx] += sizes[i]

    return levals, ask_vols, bid_vols 



@njit(cache= True)

def _calc_poc_val_vah(levels, ask_vols, bid_vols, value_area_pct):
    n = len(levels)
    if n = 0:
        return 0,0,0 
    
    total_vols = ask_vols + bid_vols 
    total_vol = 0 
    for i in range(n):
        total_vol += total_vols[i]

    if total_vol <= 0:
        mid = n//2 
        return levels[mid], levels[0], levels[n-1]

    poc_idx = 0 
    max_vol = -1 
    for i in range(n):
        if total_vols[i]>max_vol:
            max_vol = total_vols[i]
            poc_idx = i 

    target = total_vol * value_area_pct 
    acc    = total_vols[poc_idx]
    lo     = poc_idx 
    hi     = poc_idx 


    while acc < target:
        can_up = hi + 1 <n 
        can_dn = lo - 1 >= 0 
        if not can_up and not can_dn:
            break 

        v_up = total_vols[hi+1] if can_up else -1 
        v_dn = total_vols[lo-1] if can_dn else -1 

if v_up >= v_dn:
            hi += 1 
            acc+= total_vols[hi]
        else:
            lo -= 1 
            acc+= total_vols[lo]


    return levels[poc_idx], levels[lo], levels[hi]



    
    























