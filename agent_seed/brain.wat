(module
  ;; action: 0=N, 1=E, 2=S, 3=W
  ;; walls: N=1, E=2, S=4, W=8 (set bit = blocked)
  (func (export "decide")
    (param $px i32) (param $py i32) (param $gx i32) (param $gy i32)
    (param $walls i32) (param $step i32) (param $steps_left i32)
    (param $width i32) (param $height i32) (param $advice i64)
    (result i32)

    local.get $gx local.get $px i32.gt_s
    if
      local.get $walls i32.const 2 i32.and i32.eqz
      if i32.const 1 return end
    end

    local.get $gx local.get $px i32.lt_s
    if
      local.get $walls i32.const 8 i32.and i32.eqz
      if i32.const 3 return end
    end

    local.get $gy local.get $py i32.gt_s
    if
      local.get $walls i32.const 4 i32.and i32.eqz
      if i32.const 2 return end
    end

    local.get $gy local.get $py i32.lt_s
    if
      local.get $walls i32.const 1 i32.and i32.eqz
      if i32.const 0 return end
    end

    local.get $walls i32.const 1 i32.and i32.eqz
    if i32.const 0 return end
    local.get $walls i32.const 2 i32.and i32.eqz
    if i32.const 1 return end
    local.get $walls i32.const 4 i32.and i32.eqz
    if i32.const 2 return end
    i32.const 3
  )
)
