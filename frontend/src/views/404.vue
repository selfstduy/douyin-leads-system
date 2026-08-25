<template>
  <div class="not-found">
    <h1>404</h1>
    <p>页面未找到</p>
    <el-button type="primary" @click="$router.push('/dashboard')">返回首页</el-button>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.not-found {
  width: 100%;
  height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
}
.not-found h1 {
  font-size: 80px;
  color: #409eff;
}
.not-found p {
  font-size: 18px;
  color: #999;
}
</style>
