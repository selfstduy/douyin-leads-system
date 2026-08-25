<template>
  <div class="page-header">
    <h2 class="page-header__title">{{ title }}</h2>
    <div class="page-header__extra">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string
}>()
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}
.page-header__title {
  font-size: 20px;
  font-weight: 600;
  color: #333;
}
</style>
